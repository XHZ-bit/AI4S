import fitz
import pytest
from contextlib import closing
from fastapi.testclient import TestClient

from app.db.sqlite import connect, get_paper, upsert_paper
from app.main import app


def _make_pdf(text: str) -> bytes:
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc.tobytes()


def test_upload_and_get_paper(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.papers._connect", lambda: connect())
    monkeypatch.setattr("app.api.papers.merge_paper", lambda p: None)
    monkeypatch.setattr("app.api.papers._data_dir", lambda: tmp_path)

    client = TestClient(app)
    resp = client.post(
        "/api/papers/upload",
        files={"file": ("demo.pdf", _make_pdf("My Uploaded Paper Title"), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"].startswith("upload-")
    assert body["parse_status"] == "parsed"

    got = client.get(f"/api/papers/{body['uid']}").json()
    assert got["source"] == "upload"
    assert got["title"]
    assert (tmp_path / f"{body['uid']}.pdf").exists()

    listing = client.get("/api/papers").json()
    assert listing["total"] == 1
    assert listing["items"][0]["uid"] == body["uid"]

    missing = client.get("/api/papers/nonexistent")
    assert missing.status_code == 404


def test_upload_fulltext_preserves_collected_abstract_when_fallback_has_none(monkeypatch):
    monkeypatch.setattr("app.api.papers.merge_paper", lambda p: None)
    monkeypatch.setattr("app.api.papers.index_paper", lambda *args: None)
    with closing(connect()) as conn:
        upsert_paper(conn, {
            "uid": "collected", "arxiv_id": None, "title": "Collected title",
            "abstract": "A useful abstract from the paper collection service.",
            "authors": ["Researcher"], "year": 2026, "venue": None,
            "categories": [], "published": None, "pdf_url": None,
            "code_url": None, "source": "arxiv",
        })

    response = TestClient(app).post(
        "/api/papers/upload", params={"uid": "collected"},
        files={"file": ("paper.pdf", _make_pdf("Full paper title"), "application/pdf")},
    )
    assert response.status_code == 200
    with closing(connect()) as conn:
        paper = get_paper(conn, "collected")
        assert paper["abstract"] == "A useful abstract from the paper collection service."
        assert paper["title"] == "Full paper title"
        assert paper["parse_status"] == "parsed"


@pytest.mark.parametrize("endpoint", ["/api/papers/upload", "/api/papers/upload-async"])
@pytest.mark.parametrize("kind", ["damaged", "encrypted"])
def test_unreadable_upload_is_rejected_before_persistence(endpoint, kind, monkeypatch):
    from app.api.papers import _data_dir

    if kind == "damaged":
        raw = b"%PDF-1.4\nThis is not a readable PDF document."
    else:
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Password protected paper")
            raw = document.tobytes(
                encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="reader",
            )
    monkeypatch.setattr("app.jobs.enqueue", lambda *args: pytest.fail("invalid PDF must not be queued"))
    response = TestClient(app).post(
        endpoint, files={"file": ("unreadable.pdf", raw, "application/pdf")},
    )
    assert response.status_code == 422
    assert "重新上传" in response.json()["detail"]
    assert list(_data_dir().glob("*.pdf")) == []
    with closing(connect()) as conn:
        for table in ("papers", "documents", "tasks", "pipeline_stages"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
