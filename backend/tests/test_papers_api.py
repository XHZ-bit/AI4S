import fitz
from fastapi.testclient import TestClient

from app.db.sqlite import connect
from app.main import app


def _make_pdf(text: str) -> bytes:
    doc = fitz.open()
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
