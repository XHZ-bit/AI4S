"""Queue admission failures must acknowledge the already-saved original."""

import hashlib
from concurrent.futures import Future
from contextlib import closing

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import accounts, jobs
from app.config import get_settings
from app.db.sqlite import connect
from app.main import app
from app.tenancy import data_dir, user_scope


@pytest.fixture
def uploader(monkeypatch):
    monkeypatch.setenv("ACCESS_MODE", "multiuser")
    get_settings.cache_clear()
    password = "Saved originals must have clear upload receipts"
    owner = accounts.create_user("uploader", password)
    client = TestClient(app, base_url="https://testserver")
    response = client.post("/api/auth/login", json={"username": "uploader", "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-Atlas-CSRF"] = response.json()["csrf_token"]
    try:
        yield client, owner
    finally:
        client.close()


def _pdf(text):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), text)
        return pdf.tobytes()


def _upload(client, raw):
    return client.post("/api/papers/upload-async", files={"file": ("paper.pdf", raw, "application/pdf")})


def _assert_saved_not_queued(response, raw, owner, *, papers, tasks):
    uid = "upload-" + hashlib.sha256(raw).hexdigest()[:24]
    assert response.status_code == 429, response.text
    receipt = response.json()
    assert {key: receipt[key] for key in ("saved", "uid", "parse_status", "retryable")} == {
        "saved": True, "uid": uid, "parse_status": "not_queued", "retryable": True,
    }
    assert isinstance(receipt["detail"], str)
    assert "原文已保存，尚未排入解析" in receipt["detail"]
    assert "无需重新上传" in receipt["detail"]
    with user_scope(owner), closing(connect()) as conn:
        assert (data_dir() / "pdfs" / f"{uid}.pdf").read_bytes() == raw
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == papers
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == tasks
        assert conn.execute("SELECT parse_status FROM papers WHERE uid=?", (uid,)).fetchone()[0] == "pending"
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE params_json LIKE ?", (f"%{uid}%",)).fetchone()[0] == 0
    return uid


def test_second_upload_acknowledges_saved_file_when_personal_task_is_active(uploader, monkeypatch):
    client, owner = uploader
    futures = []

    def pending(*_args):
        future = Future()
        futures.append(future)
        return future

    monkeypatch.setattr(jobs, "submit_task", pending)
    try:
        raw_first, raw_second = _pdf("First queued original"), _pdf("Second saved original")
        first = _upload(client, raw_first)
        assert first.status_code == 202
        assert first.json() == {
            "uid": "upload-" + hashlib.sha256(raw_first).hexdigest()[:24],
            "task_id": 1, "parse_status": "queued",
        }
        duplicate = _upload(client, raw_first)
        assert duplicate.status_code == 202 and duplicate.json() == first.json()
        uid = _assert_saved_not_queued(_upload(client, raw_second), raw_second, owner, papers=2, tasks=1)
        assert len(futures) == 1
        # The saved UID can resume through the parse endpoint without sending a
        # second multipart body or creating another paper/file.
        assert client.post("/api/system/tasks/legacy/1/cancel").status_code == 200
        retry = client.post(f"/api/papers/{uid}/parse")
        assert retry.status_code == 202 and retry.json() == {"task_id": 2}
        with user_scope(owner), closing(connect()) as conn:
            assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2
            assert len(list((data_dir() / "pdfs").glob("*.pdf"))) == 2
    finally:
        for future in futures:
            future.cancel()


def test_upload_acknowledges_saved_file_when_global_queue_capacity_is_full(uploader):
    client, owner = uploader
    acquired = 0
    try:
        while jobs._slots.acquire(blocking=False):
            acquired += 1
        assert acquired == 24
        raw = _pdf("Preserved despite a full shared queue")
        response = _upload(client, raw)
        _assert_saved_not_queued(response, raw, owner, papers=1, tasks=0)
        assert "队列已满" in response.json()["detail"]
    finally:
        for _ in range(acquired):
            jobs._slots.release()
