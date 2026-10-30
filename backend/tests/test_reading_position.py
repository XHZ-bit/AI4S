"""Document-bound resume state, real page limits, and private user storage."""

import hashlib
from contextlib import closing
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.config import get_settings
from app.db.sqlite import _initialized_paths, connect
from app.db.workspace import get_state, put_state, save_document
from app.main import app
from app.models.paper import ParsedPaper, Section
from app.paper_quality import record_quality
from app.tenancy import data_dir, user_scope


def _seed(conn, uid="paper-1", pages=3, title="Original paper", quality=True, save_pdf=True):
    with pymupdf.open() as pdf:
        for page in range(pages):
            pdf.new_page().insert_text((72, 72), f"{title} page {page + 1}")
        raw = pdf.tobytes()
    conn.execute("INSERT OR IGNORE INTO papers(uid,title) VALUES(?,?)", (uid, title))
    conn.commit()
    parsed = ParsedPaper(uid=uid, title=title, abstract="", sections=[
        Section(heading="Method", text=f"{title} evidence", page=1),
    ])
    digest = hashlib.sha256(raw).hexdigest()
    did = save_document(conn, uid, parsed, digest, f"{uid}.pdf")
    if quality:
        record_quality(conn, uid, did, raw, parsed)
    if save_pdf:
        folder = data_dir() / "pdfs"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{uid}.pdf").write_bytes(raw)
    return did, digest


@pytest.fixture
def paper():
    with closing(connect()) as conn:
        return _seed(conn)


def test_old_database_gets_additive_reading_position_table():
    with closing(connect()) as conn:
        _seed(conn)
        conn.execute("DROP TABLE paper_reading_positions")
        conn.commit()
    _initialized_paths.clear()
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM paper_reading_positions").fetchone()[0] == 0


def test_position_starts_null_persists_and_repeated_put_is_idempotent(paper):
    did, digest = paper
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    assert client.get(url, params={"document_id": did}).json() == {"position": None}
    saved = client.put(url, json={"document_id": did, "page": 2})
    assert saved.status_code == 200, saved.text
    position = saved.json()["position"]
    assert {key: position[key] for key in ("paper_uid", "document_id", "document_version", "page", "page_count")} == {
        "paper_uid": "paper-1", "document_id": did, "document_version": f"sha256:{digest}",
        "page": 2, "page_count": 3,
    }
    assert position["updated_at"]
    _initialized_paths.clear()
    assert TestClient(app).get(url, params={"document_id": did}).json() == saved.json()
    with closing(connect()) as conn:
        conn.execute("UPDATE paper_reading_positions SET updated_at='before-slow-network-retry'")
        conn.commit()
    retry = client.put(url, json={"document_id": did, "page": 2})
    assert retry.json()["position"]["updated_at"] == "before-slow-network-retry"
    changed = client.put(url, json={"document_id": did, "page": 3})
    assert changed.json()["position"]["page"] == 3
    assert changed.json()["position"]["updated_at"] != "before-slow-network-retry"


@pytest.mark.parametrize("page", [0, -1, 1.5, 1.0, "2", True, False, None, [], {}])
def test_page_must_be_a_strict_positive_integer(paper, page):
    did, _ = paper
    response = TestClient(app).put("/api/papers/paper-1/reading-position", json={"document_id": did, "page": page})
    assert response.status_code == 422
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_reading_positions").fetchone()[0] == 0


def test_page_limits_use_measured_pdf_pages_not_highest_extracted_passage_page(paper):
    did, _ = paper
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    assert client.put(url, json={"document_id": did, "page": 3}).status_code == 200
    assert client.put(url, json={"document_id": did, "page": 4}).status_code == 422
    assert client.get(url, params={"document_id": did}).json()["position"]["page"] == 3


@pytest.mark.parametrize("body", [
    {}, {"page": 1}, {"document_id": ""}, {"document_id": 123, "page": 1},
    {"document_id": "unknown", "page": 1, "complete": True},
])
def test_missing_or_unexpected_position_fields_are_rejected(body):
    assert TestClient(app).put("/api/papers/paper-1/reading-position", json=body).status_code == 422


def test_paper_and_document_membership_are_checked_on_get_and_put(paper):
    did, _ = paper
    with closing(connect()) as conn:
        _seed(conn, uid="other", pages=1)
    client = TestClient(app)
    for uid, document_id in (("other", did), ("missing", did), ("paper-1", "missing")):
        url = f"/api/papers/{uid}/reading-position"
        assert client.get(url, params={"document_id": document_id}).status_code == 404
        assert client.put(url, json={"document_id": document_id, "page": 1}).status_code == 404
    assert client.get("/api/papers/paper-1/reading-position").status_code == 422


def test_each_document_version_retains_its_own_position_and_page_bounds():
    with closing(connect()) as conn:
        old, old_hash = _seed(conn, pages=4, title="Historical version")
        new, new_hash = _seed(conn, pages=2, title="Current version")
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    first = client.put(url, json={"document_id": old, "page": 4})
    second = client.put(url, json={"document_id": new, "page": 2})
    assert first.status_code == second.status_code == 200
    assert first.json()["position"]["document_version"] == f"sha256:{old_hash}"
    assert second.json()["position"]["document_version"] == f"sha256:{new_hash}"
    assert client.get(url, params={"document_id": old}).json() == first.json()
    assert client.get(url, params={"document_id": new}).json() == second.json()
    assert client.put(url, json={"document_id": new, "page": 3}).status_code == 422


def test_legacy_document_without_quality_uses_only_its_matching_pdf():
    with closing(connect()) as conn:
        old, _ = _seed(conn, pages=2, quality=False)
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    saved = client.put(url, json={"document_id": old, "page": 2})
    assert saved.status_code == 200 and saved.json()["position"]["page_count"] == 2
    assert client.put(url, json={"document_id": old, "page": 3}).status_code == 422
    with closing(connect()) as conn:
        _seed(conn, pages=5, title="A different latest PDF", quality=False)
    assert client.put(url, json={"document_id": old, "page": 4}).status_code == 409
    assert client.get(url, params={"document_id": old}).json() == saved.json()


def test_missing_or_invalid_quality_cannot_invent_a_page_limit():
    with closing(connect()) as conn:
        did, _ = _seed(conn, quality=False, save_pdf=False)
        conn.execute("INSERT INTO paper_parse_quality VALUES(?,?,'{malformed')", (did, "paper-1"))
        conn.commit()
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    assert client.get(url, params={"document_id": did}).json() == {"position": None}
    assert client.put(url, json={"document_id": did, "page": 1}).status_code == 409


def test_mutated_document_hash_cannot_reuse_a_saved_position(paper):
    did, _ = paper
    client = TestClient(app)
    url = "/api/papers/paper-1/reading-position"
    assert client.put(url, json={"document_id": did, "page": 1}).status_code == 200
    with closing(connect()) as conn:
        conn.execute("UPDATE documents SET content_hash='different-version' WHERE id=?", (did,))
        conn.commit()
    assert client.get(url, params={"document_id": did}).status_code == 409
    assert client.put(url, json={"document_id": did, "page": 2}).status_code == 409


def test_navigation_does_not_modify_learning_or_mastery(paper):
    did, _ = paper
    with closing(connect()) as conn:
        put_state(conn, "paper-1", {"reading": {"read:passage-1": True}, "answers": {"problem": "My answer"}}, 0)
        conn.execute("INSERT INTO workflow_mastery(concept_uid,confirmed,version,reason) VALUES('c1',1,2,'Explicit')")
        conn.commit()
        state = get_state(conn, "paper-1")
        mastery = dict(conn.execute("SELECT * FROM workflow_mastery").fetchone())
        paper_before = dict(conn.execute("SELECT * FROM papers").fetchone())
    client = TestClient(app)
    for page in (1, 2, 3, 2):
        assert client.put("/api/papers/paper-1/reading-position", json={"document_id": did, "page": page}).status_code == 200
    with closing(connect()) as conn:
        assert get_state(conn, "paper-1") == state
        assert dict(conn.execute("SELECT * FROM workflow_mastery").fetchone()) == mastery
        assert dict(conn.execute("SELECT * FROM papers").fetchone()) == paper_before
        assert conn.execute("SELECT COUNT(*) FROM workflow_mastery_events").fetchone()[0] == 0


def test_authenticated_users_keep_independent_positions_for_identical_document_ids(monkeypatch):
    monkeypatch.setenv("ACCESS_MODE", "multiuser")
    get_settings.cache_clear()
    password = "Independent exact document reading positions"
    users = {name: accounts.create_user(name, password) for name in ("alice", "bob")}
    document_id = "same-document-id"
    for name, user in users.items():
        with user_scope(user), closing(connect()) as conn:
            did, _ = _seed(conn)
            # Real identical IDs in separate account databases must stay private.
            conn.execute("UPDATE documents SET id=? WHERE id=?", (document_id, did))
            conn.execute("UPDATE paper_parse_quality SET document_id=? WHERE document_id=?", (document_id, did))
            if name == "alice":
                _seed(conn, uid="alice-only")
            conn.commit()
    clients = {name: TestClient(app, base_url="https://testserver") for name in users}
    anonymous = TestClient(app, base_url="https://testserver")
    try:
        for name, client in clients.items():
            response = client.post("/api/auth/login", json={"username": name, "password": password})
            assert response.status_code == 200, response.text
            client.headers["X-Atlas-CSRF"] = response.json()["csrf_token"]
        url = "/api/papers/paper-1/reading-position"
        assert clients["alice"].put(url, json={"document_id": document_id, "page": 3}).status_code == 200
        assert clients["bob"].get(url, params={"document_id": document_id}).json() == {"position": None}
        assert clients["bob"].put(url, json={"document_id": document_id, "page": 1}).status_code == 200
        assert clients["alice"].get(url, params={"document_id": document_id}).json()["position"]["page"] == 3
        assert clients["bob"].get(url, params={"document_id": document_id}).json()["position"]["page"] == 1
        assert clients["bob"].get("/api/papers/alice-only/reading-position", params={"document_id": document_id}).status_code == 404
        clients["bob"].headers.pop("X-Atlas-CSRF")
        assert clients["bob"].put(url, json={"document_id": document_id, "page": 2}).status_code == 403
        assert anonymous.get(url, params={"document_id": document_id}).status_code == 401
        assert anonymous.put(url, json={"document_id": document_id, "page": 2}).status_code == 401
        assert not (Path(get_settings().data_dir) / "atlas.db").exists()
    finally:
        anonymous.close()
        for client in clients.values():
            client.close()
