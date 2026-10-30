"""The personal shelf persists flags without changing evidence or learning state."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.config import get_settings
from app.db import library
from app.db.sqlite import _initialized_paths, connect
from app.db.workspace import get_state, put_state
from app.main import app
from app.tenancy import user_scope


@pytest.fixture
def client():
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def _seed(conn, uid="paper-1", title="Evidence for learning", abstract="A useful method",
          parse_status="parsed", created_at="2026-10-19 10:00:00"):
    conn.execute(
        "INSERT INTO papers(uid,title,abstract,authors_json,year,source,parse_status,created_at) "
        "VALUES(?,?,?,?,2026,'upload',?,?)",
        (uid, title, abstract, json.dumps(["Researcher A"]), parse_status, created_at),
    )
    conn.commit()


def test_existing_papers_get_default_flags_without_backfilling_learning_data(tmp_path):
    path = str(tmp_path / "legacy.db")
    with closing(sqlite3.connect(path)) as old:
        old.execute("CREATE TABLE papers(uid TEXT PRIMARY KEY,title TEXT NOT NULL,"
                    "abstract TEXT DEFAULT '',authors_json TEXT DEFAULT '[]',year INTEGER,"
                    "source TEXT DEFAULT 'arxiv',parse_status TEXT DEFAULT 'pending',"
                    "created_at TEXT DEFAULT (datetime('now')))")
        old.execute("INSERT INTO papers(uid,title) VALUES('existing','Existing paper')")
        old.commit()
    with closing(connect(path)) as conn:
        item = library.list_papers(conn)["items"][0]
        assert (item["uid"], item["starred"], item["read_later"], item["library_updated_at"]) == (
            "existing", False, False, None,
        )
        assert conn.execute("SELECT COUNT(*) FROM paper_library").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM workflow_mastery").fetchone()[0] == 0


def test_flags_persist_across_connections_and_schema_reinitialization(client):
    with closing(connect()) as conn:
        _seed(conn)
    response = client.patch("/api/library/papers/paper-1", json={"starred": True})
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["starred"] is True and first["read_later"] is False
    assert first["library_updated_at"] is not None
    assert first["authors"] == ["Researcher A"]
    assert first["title"] == "Evidence for learning" and first["year"] == 2026
    _initialized_paths.clear()
    listed = client.get("/api/library/papers").json()
    assert listed == {"total": 1, "items": [first]}
    assert client.get("/api/library/summary").json() == {"all": 1, "starred": 1, "read_later": 0}


def test_repeated_explicit_updates_are_idempotent_and_omitted_flags_are_preserved(client):
    with closing(connect()) as conn:
        _seed(conn)
    # Setting an existing default does not manufacture a changed timestamp.
    default = client.patch("/api/library/papers/paper-1", json={"starred": False}).json()
    assert default["library_updated_at"] is None
    client.patch("/api/library/papers/paper-1", json={"starred": True})
    with closing(connect()) as conn:
        conn.execute("UPDATE paper_library SET updated_at='recorded-before-retry'")
        conn.commit()
    retry = client.patch("/api/library/papers/paper-1", json={"starred": True})
    assert retry.status_code == 200
    assert retry.json()["library_updated_at"] == "recorded-before-retry"
    later = client.patch("/api/library/papers/paper-1", json={"read_later": True}).json()
    assert later["starred"] is True and later["read_later"] is True
    assert later["library_updated_at"] != "recorded-before-retry"
    assert client.patch("/api/library/papers/paper-1", json={"read_later": True}).json() == later
    removed = client.patch("/api/library/papers/paper-1", json={"starred": False, "read_later": False}).json()
    assert removed["starred"] is False and removed["read_later"] is False
    assert client.get("/api/library/summary").json() == {"all": 1, "starred": 0, "read_later": 0}


def test_filter_search_parse_status_and_pagination_use_the_same_result_set(client):
    with closing(connect()) as conn:
        _seed(conn, "a", "中文论文", "A graph method", created_at="2026-10-18 10:00:00")
        _seed(conn, "b", "Graph study", "A second method", parse_status="pending")
        _seed(conn, "c", "Unrelated paper", "Third abstract")
        library.set_flags(conn, "a", {"starred": True, "read_later": True})
        library.set_flags(conn, "b", {"starred": True})
    all_papers = client.get("/api/library/papers", params={"limit": 2}).json()
    assert all_papers["total"] == 3
    assert [item["uid"] for item in all_papers["items"]] == ["b", "c"]
    page = client.get("/api/library/papers", params={"filter": "starred", "q": "graph", "limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and [item["uid"] for item in page["items"]] == ["a"]
    parsed = client.get("/api/library/papers", params={"filter": "starred", "q": "graph", "parse_status": "parsed"}).json()
    assert parsed["total"] == 1 and parsed["items"][0]["uid"] == "a"
    assert client.get("/api/library/papers", params={"q": "中文"}).json()["total"] == 1
    assert [item["uid"] for item in client.get("/api/library/papers?filter=read_later").json()["items"]] == ["a"]
    assert client.get("/api/library/papers", params={"filter": "starred", "q": "missing"}).json() == {"total": 0, "items": []}
    assert client.get("/api/library/summary").json() == {"all": 3, "starred": 2, "read_later": 1}


def test_empty_library_summary_and_page(client):
    assert client.get("/api/library/summary").json() == {"all": 0, "starred": 0, "read_later": 0}
    assert client.get("/api/library/papers").json() == {"total": 0, "items": []}


def test_local_runtime_reports_only_the_enforced_local_upload_limit(client, monkeypatch):
    from app.api.papers import _MAX_PDF_BYTES

    monkeypatch.setattr("app.api.system.graph_status", lambda: {"status": "unavailable"})
    monkeypatch.setattr("app.api.system.parser_status", lambda: {"status": "fallback"})
    assert client.get("/api/system/status").json()["limits"] == {
        "pdf_max_bytes": _MAX_PDF_BYTES, "pdf_max_pages": None,
        "max_papers": None, "storage_max_bytes": None,
    }


@pytest.mark.parametrize("body", [
    {}, {"starred": None}, {"read_later": None}, {"starred": 1}, {"read_later": 0},
    {"starred": "true"}, {"read_later": "false"}, {"starred": []},
    {"starred": True, "read_later": None}, {"starred": True, "unexpected": False}, [], True,
])
def test_patch_rejects_empty_or_non_boolean_flags_without_writes(client, body):
    with closing(connect()) as conn:
        _seed(conn)
    assert client.patch("/api/library/papers/paper-1", json=body).status_code == 422
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_library").fetchone()[0] == 0


@pytest.mark.parametrize("params", [
    {"filter": "unknown"}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "nan"},
])
def test_list_rejects_invalid_pagination_or_filter(client, params):
    assert client.get("/api/library/papers", params=params).status_code == 422


def test_missing_paper_cannot_create_orphan_flags(client):
    assert client.patch("/api/library/papers/missing", json={"starred": True}).status_code == 404
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM paper_library").fetchone()[0] == 0


def test_shelf_updates_do_not_change_learning_mastery_or_paper_metadata(client):
    with closing(connect()) as conn:
        _seed(conn)
        put_state(conn, "paper-1", {"reading": {"passage-1": True}, "answers": {"problem": "My notes"}}, 0)
        conn.execute("INSERT INTO workflow_mastery(concept_uid,confirmed,version,reason) "
                     "VALUES('concept-1',1,4,'Explicit learner confirmation')")
        conn.commit()
        state = get_state(conn, "paper-1")
        mastery = dict(conn.execute("SELECT * FROM workflow_mastery").fetchone())
        paper = dict(conn.execute("SELECT * FROM papers").fetchone())
    for body in ({"starred": True}, {"read_later": True}, {"starred": False, "read_later": False}):
        assert client.patch("/api/library/papers/paper-1", json=body).status_code == 200
    with closing(connect()) as conn:
        assert get_state(conn, "paper-1") == state
        assert dict(conn.execute("SELECT * FROM workflow_mastery").fetchone()) == mastery
        assert dict(conn.execute("SELECT * FROM papers").fetchone()) == paper
        assert conn.execute("SELECT COUNT(*) FROM workflow_mastery_events").fetchone()[0] == 0


def test_concurrent_partial_edits_preserve_both_flags(tmp_path):
    path = str(tmp_path / "concurrent.db")
    with closing(connect(path)) as conn:
        _seed(conn)
    start = Barrier(3)

    def edit(changes):
        with closing(connect(path)) as conn:
            start.wait(timeout=5)
            return library.set_flags(conn, "paper-1", changes)

    with ThreadPoolExecutor(max_workers=2) as pool:
        starred = pool.submit(edit, {"starred": True})
        read_later = pool.submit(edit, {"read_later": True})
        start.wait(timeout=5)
        starred.result(timeout=10)
        read_later.result(timeout=10)
    with closing(connect(path)) as conn:
        item = library.paper_item(conn, "paper-1")
        assert item["starred"] is True and item["read_later"] is True
        assert conn.execute("SELECT COUNT(*) FROM paper_library").fetchone()[0] == 1


def test_failed_edit_rolls_back_and_releases_transaction():
    with closing(connect()) as conn:
        _seed(conn)
        original = library.set_flags(conn, "paper-1", {"starred": True})
        conn.execute("CREATE TRIGGER reject_later BEFORE UPDATE ON paper_library "
                     "WHEN NEW.read_later=1 BEGIN SELECT RAISE(ABORT,'synthetic write failure'); END")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="synthetic write failure"):
            library.set_flags(conn, "paper-1", {"starred": False, "read_later": True})
        assert not conn.in_transaction
        assert library.paper_item(conn, "paper-1") == original
        assert library.set_flags(conn, "paper-1", {"starred": False})["starred"] is False


def test_two_real_accounts_have_private_shelves_even_with_the_same_paper_uid(monkeypatch):
    monkeypatch.setenv("ACCESS_MODE", "multiuser")
    monkeypatch.setenv("USER_PDF_MAX_BYTES", "12345")
    monkeypatch.setenv("USER_PDF_MAX_PAGES", "3")
    monkeypatch.setenv("USER_MAX_PAPERS", "4")
    monkeypatch.setenv("USER_STORAGE_MAX_BYTES", "2345678")
    get_settings.cache_clear()
    password = "Independent paper shelves for invited users"
    users = {name: accounts.create_user(name, password) for name in ("alice", "bob")}
    for name, user in users.items():
        with user_scope(user), closing(connect()) as conn:
            _seed(conn, title=f"{name} personal paper")
            if name == "alice":
                _seed(conn, "alice-only", "Private Alice source")
    with TestClient(app, base_url="https://testserver") as alice, TestClient(app, base_url="https://testserver") as bob:
        for name, client in (("alice", alice), ("bob", bob)):
            response = client.post("/api/auth/login", json={"username": name, "password": password})
            assert response.status_code == 200, response.text
            client.headers["X-Atlas-CSRF"] = response.json()["csrf_token"]
        assert alice.get("/api/system/status").json()["limits"] == {
            "pdf_max_bytes": 12345, "pdf_max_pages": 3,
            "max_papers": 4, "storage_max_bytes": 2345678,
        }
        assert alice.patch("/api/library/papers/paper-1", json={"starred": True}).status_code == 200
        assert bob.patch("/api/library/papers/paper-1", json={"read_later": True}).status_code == 200
        alice_items = alice.get("/api/library/papers").json()
        bob_items = bob.get("/api/library/papers").json()
        assert alice_items["total"] == 2 and bob_items["total"] == 1
        alice_paper = next(item for item in alice_items["items"] if item["uid"] == "paper-1")
        assert alice_paper["title"] == "alice personal paper"
        assert alice_paper["starred"] is True and alice_paper["read_later"] is False
        assert bob_items["items"][0]["title"] == "bob personal paper"
        assert bob_items["items"][0]["starred"] is False and bob_items["items"][0]["read_later"] is True
        assert bob.patch("/api/library/papers/alice-only", json={"starred": True}).status_code == 404
        assert bob.get("/api/library/papers", params={"q": "Private Alice"}).json()["total"] == 0
        assert alice.get("/api/library/summary").json() == {"all": 2, "starred": 1, "read_later": 0}
        assert bob.get("/api/library/summary").json() == {"all": 1, "starred": 0, "read_later": 1}
        bob.headers.pop("X-Atlas-CSRF")
        assert bob.patch("/api/library/papers/paper-1", json={"starred": True}).status_code == 403
    with TestClient(app, base_url="https://testserver") as anonymous:
        assert anonymous.get("/api/library/papers").status_code == 401
        assert anonymous.get("/api/library/summary").status_code == 401
        assert anonymous.patch("/api/library/papers/paper-1", json={"starred": True}).status_code == 401
