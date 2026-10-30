"""Exercise the real HTTP boundary and workers against separate user databases."""

import hashlib
from concurrent.futures import Future
from contextlib import closing
from pathlib import Path
from threading import Event, get_ident
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from app import accounts
from app.config import get_settings
from app.db import projects as project_store
from app.db.sqlite import connect
from app.db.workspace import save_document
from app.main import app
from app.models.paper import ParsedPaper, Section
from app.models.research import ErrorDetail, TaskKind, TaskStatus
from app.tasks import shutdown_executor, submit_task
from app.tenancy import current_user, data_dir, user_scope
from tests.test_research_t1_storage import seed_snapshot

PASSWORD = "invited users choose long passwords"


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setenv("ACCESS_MODE", "multiuser")
    # A local developer's configured key must not turn on paid/shared services.
    monkeypatch.setenv("DASHSCOPE_API_KEY", "synthetic-configured-local-key")
    monkeypatch.setenv("RESEARCH_MODEL_ENABLED", "true")
    get_settings.cache_clear()
    shutdown_executor(wait=True)
    settings = get_settings()
    users = {name: accounts.create_user(name, PASSWORD, "admin" if name == "admin" else "user")
             for name in ("admin", "alice", "bob")}
    clients = {}
    with TestClient(app, base_url="https://testserver") as anonymous:
        for name in users:
            client = TestClient(app, base_url="https://testserver")
            response = client.post("/api/auth/login", json={"username": name, "password": PASSWORD})
            assert response.status_code == 200, response.text
            client.headers["X-Atlas-CSRF"] = response.json()["csrf_token"]
            clients[name] = client
        try:
            yield SimpleNamespace(settings=settings, users=users, clients=clients, anonymous=anonymous,
                                  root=Path(settings.data_dir))
        finally:
            shutdown_executor(wait=True)
            for client in clients.values():
                client.close()
    assert current_user.get() is None


def _pdf(text, pages=1):
    with pymupdf.open() as document:
        for _ in range(pages):
            document.new_page().insert_text((72, 72), text)
        return document.tobytes()


def _seed_paper(user, uid, title):
    raw = _pdf(title)
    with user_scope(user), closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title,abstract,year,source,parse_status) "
                     "VALUES(?,?,?,2026,'upload','parsed')", (uid, title, title + " abstract"))
        conn.commit()
        folder = data_dir() / "pdfs"
        folder.mkdir(exist_ok=True)
        (folder / f"{uid}.pdf").write_bytes(raw)
        save_document(conn, uid, ParsedPaper(uid=uid, title=title, abstract="",
                                            sections=[Section(heading="Method", text=title, page=1)]),
                      hashlib.sha256(raw).hexdigest(), f"{uid}.pdf")
    return raw


def _project(client, title):
    response = client.post("/api/projects", json={
        "title": title, "research_question": "Which candidate should be verified?",
        "domain": "image_anomaly_detection", "constraints": {"version": 1, "objective": "Minimum validation"},
    })
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, raw, filename="paper.pdf"):
    return client.post("/api/papers/upload-async", files={"file": (filename, raw, "application/pdf")})


@pytest.mark.parametrize("path", [
    "/api/papers", "/api/papers/shared/file", "/api/learning/papers/shared",
    "/api/projects", "/api/system/tasks", "/api/system/status",
    "/api/projects/project-secret/snapshots/snapshot-1/export?format=json",
])
def test_anonymous_cannot_read_api_pdf_or_export(shared, path):
    response = shared.anonymous.get(path)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert not (shared.root / "atlas.db").exists()


def test_same_paper_ids_files_and_reading_data_are_private(shared):
    alice, bob = shared.clients["alice"], shared.clients["bob"]
    raw_a = _seed_paper(shared.users["alice"], "shared", "Alice private full text")
    raw_b = _seed_paper(shared.users["bob"], "shared", "Bob independent full text")
    _seed_paper(shared.users["alice"], "alice-only", "Alice only")
    assert alice.get("/api/papers/shared").json()["title"] == "Alice private full text"
    assert bob.get("/api/papers/shared").json()["title"] == "Bob independent full text"
    assert alice.get("/api/papers/shared/file").content == raw_a
    assert bob.get("/api/papers/shared/file").content == raw_b
    assert raw_a != raw_b
    assert bob.get("/api/papers/alice-only").status_code == 404
    assert bob.get("/api/papers/alice-only/file").status_code == 404
    assert bob.patch("/api/papers/alice-only", json={"title": "Overwritten"}).status_code == 404
    assert alice.patch("/api/papers/shared", json={"title": "Alice changed title"}).status_code == 200
    assert bob.get("/api/papers/shared").json()["title"] == "Bob independent full text"
    for client, note in ((alice, "Alice private note"), (bob, "Bob private note")):
        response = client.patch("/api/learning/papers/shared", json={"version": 0, "state": {"answers": {"problem": note}}})
        assert response.status_code == 200, response.text
        assert client.get("/api/learning/papers/shared").json()["state"]["answers"]["problem"] == note
    assert "Alice private note" not in bob.get("/api/learning/papers/shared").text
    assert bob.patch("/api/learning/papers/alice-only", json={"version": 0, "state": {"answers": {}}}).status_code == 404
    assert not (shared.root / "atlas.db").exists()


def test_projects_and_snapshot_exports_are_private(shared):
    alice, bob = shared.clients["alice"], shared.clients["bob"]
    project_a = _project(alice, "Alice secret project")
    project_b = _project(bob, "Bob independent project")
    assert [item["id"] for item in alice.get("/api/projects").json()["items"]] == [project_a["id"]]
    assert [item["id"] for item in bob.get("/api/projects").json()["items"]] == [project_b["id"]]
    assert bob.get(f"/api/projects/{project_a['id']}").status_code == 404
    assert bob.patch(f"/api/projects/{project_a['id']}", json={"expected_version": 1, "title": "Attacker"}).status_code == 404
    assert alice.get(f"/api/projects/{project_a['id']}").json()["title"] == "Alice secret project"
    with user_scope(shared.users["alice"]), closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES('paper-1','Secret source')")
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES('doc-1','paper-1','abc123','fulltext')")
        conn.execute("INSERT INTO passages(id,document_id,heading,text,page,ordinal) "
                     "VALUES('passage-1','doc-1','Method','Method A',1,0)")
        conn.commit()
    linked = alice.post(f"/api/projects/{project_a['id']}/papers", json={
        "expected_project_version": 1, "paper_uid": "paper-1", "role": "primary",
    })
    assert linked.status_code == 201, linked.text
    with user_scope(shared.users["alice"]), closing(connect()) as conn:
        snapshot, _ = seed_snapshot(conn, project_store.get_project(conn, project_a["id"]),
                                    project_store.get_paper_link(conn, linked.json()["id"]))
    url = f"/api/projects/{project_a['id']}/snapshots/{snapshot.id}"
    assert alice.get(url + "/export?format=json").json()["project_id"] == project_a["id"]
    assert alice.get(url + "/export").status_code == 200
    for client in (bob, shared.clients["admin"]):
        assert client.get(url).status_code == 404
        assert client.get(url + "/export?format=json").status_code == 404
        assert client.get(url + "/export").status_code == 404


def test_legacy_task_id_collisions_cannot_cancel_other_users_future(shared, monkeypatch):
    import app.jobs as jobs

    submitted = []

    def queue(*args):
        future = Future()
        submitted.append(future)
        return future

    monkeypatch.setattr(jobs, "submit_task", queue)
    alice, bob = shared.clients["alice"], shared.clients["bob"]
    try:
        uploaded_a = _upload(alice, _pdf("Alice queued original"))
        uploaded_b = _upload(bob, _pdf("Bob queued original"))
        assert uploaded_a.status_code == uploaded_b.status_code == 202
        assert uploaded_a.json()["task_id"] == uploaded_b.json()["task_id"] == 1
        assert alice.get("/api/system/tasks").json()["items"][0]["label"] == uploaded_a.json()["uid"]
        assert bob.get("/api/system/tasks").json()["items"][0]["label"] == uploaded_b.json()["uid"]
        assert alice.post("/api/system/tasks/legacy/1/cancel").status_code == 200
        assert submitted[0].cancelled() and not submitted[1].cancelled()
        assert bob.get("/api/learning/tasks/1").json()["status"] == "queued"
        retry = alice.post("/api/learning/tasks/1/retry")
        assert retry.status_code == 202 and retry.json()["task_id"] == 2
        assert bob.get("/api/learning/tasks/2").status_code == 404
        assert bob.post("/api/learning/tasks/2/retry").status_code == 404
        assert bob.post("/api/system/tasks/legacy/2/cancel").status_code == 404
        assert alice.get("/api/system/tasks").json()["total"] == 2
        assert bob.get("/api/system/tasks").json()["total"] == 1
        assert not submitted[1].cancelled() and not submitted[2].cancelled()
    finally:
        for future in submitted:
            future.cancel()


def test_unified_knowledge_graph_source_file_and_learning_remain_account_scoped(shared):
    from app.knowledge import extraction, sources, store

    alice, bob = shared.clients["alice"], shared.clients["bob"]
    project = _project(alice, "Private knowledge fixture")
    pid = project["id"]
    with user_scope(shared.users["alice"]):
        source = sources.ingest(pid, b"# Synthetic private method\n\nAn account isolation fixture.", "private-fixture.md", "report")
        node = extraction.node(source, "private-method", "method", "Alice private method", "Synthetic account context", [])
        with store.connection(pid) as conn:
            store.put_record(conn, "kw_nodes", node)
    root = f"/api/projects/{pid}"
    graph = alice.get(root + "/knowledge/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["label"] == "Alice private method"
    assert alice.get(root + f"/sources/{source['id']}/file").content.startswith(b"# Synthetic")
    assert alice.get(root + f"/knowledge/nodes/{node['id']}/learning").status_code == 200
    for path in ("/knowledge/graph", f"/sources/{source['id']}/file", f"/knowledge/nodes/{node['id']}/learning"):
        assert bob.get(root + path).status_code == 404
        assert shared.anonymous.get(root + path).status_code == 401
    assert not shared.settings.knowledge_model_enabled
    assert not (shared.root / "atlas.db").exists()


def test_research_task_reads_cancellation_and_retry_are_private(shared, monkeypatch):
    from app.api import projects as project_api

    alice, bob = shared.clients["alice"], shared.clients["bob"]
    project = _project(alice, "Private queued research")
    dispatched = []
    monkeypatch.setattr(project_api, "_task_dispatcher", lambda: dispatched.append)
    with user_scope(shared.users["alice"]), closing(connect()) as conn:
        task = project_store.create_task(conn, TaskKind.PLAN_GENERATION, project["id"], {"decision_id": "private-decision"})
        project_store.update_task(conn, task.id, TaskStatus.FAILED,
                                  error=ErrorDetail(code="synthetic_failure", message="Private failure", retryable=True))
    assert alice.get(f"/api/projects/tasks/{task.id}").status_code == 200
    assert bob.get(f"/api/projects/tasks/{task.id}").status_code == 404
    assert bob.post(f"/api/projects/tasks/{task.id}/retry").status_code == 404
    assert bob.post(f"/api/system/tasks/research/{task.id}/cancel").status_code == 404
    assert bob.get("/api/system/tasks").json()["total"] == 0
    retried = alice.post(f"/api/projects/tasks/{task.id}/retry")
    assert retried.status_code == 202, retried.text
    assert dispatched == [retried.json()["id"]]
    assert bob.get(f"/api/projects/tasks/{retried.json()['id']}").status_code == 404
    assert alice.post(f"/api/system/tasks/research/{retried.json()['id']}/cancel").status_code == 200


@pytest.mark.parametrize("path", [
    "/api/auth/users", "/api/review", "/api/learning/quality",
    "/api/learning/sources", "/api/learning/relations", "/api/learning/feedback",
])
def test_regular_users_cannot_enter_admin_areas(shared, path):
    assert shared.clients["alice"].get(path).status_code == 403


def test_csrf_missing_invalid_and_cross_origin_are_rejected(shared):
    client = shared.clients["alice"]
    _seed_paper(shared.users["alice"], "private", "Original title")
    token = client.headers.pop("X-Atlas-CSRF")
    assert client.patch("/api/papers/private", json={"title": "Missing CSRF"}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-Atlas-CSRF"] = "invalid"
    assert client.patch("/api/papers/private", json={"title": "Wrong CSRF"}).status_code == 403
    client.headers["X-Atlas-CSRF"] = token
    for origin in ("https://attacker.example", "null", "http://testserver"):
        assert client.patch("/api/papers/private", headers={"Origin": origin},
                            json={"title": "Cross-origin"}).status_code == 403
    assert client.patch("/api/papers/private", headers={"Origin": "https://testserver"},
                        json={"title": "Authorized change"}).status_code == 200
    assert shared.anonymous.post("/api/auth/login", headers={"Origin": "https://attacker.example"},
                                 json={"username": "alice", "password": PASSWORD}).status_code == 403


def test_real_background_executor_keeps_owner_scope_and_never_uses_legacy_db(shared):
    caller_thread = get_ident()

    def worker(title):
        with closing(connect()) as conn:
            conn.execute("INSERT INTO papers(uid,title) VALUES('same-background-id',?)", (title,))
            conn.commit()
        return str(data_dir()), get_ident()

    pending = []
    for name in ("alice", "bob"):
        with user_scope(shared.users[name]):
            pending.append((name, submit_task(worker, name + " background result")))
    for name, future in pending:
        directory, thread = future.result(timeout=10)
        assert directory == str(shared.root.absolute() / "users" / shared.users[name]["id"])
        assert thread != caller_thread
        assert shared.clients[name].get("/api/papers/same-background-id").json()["title"] == name + " background result"
    assert current_user.get() is None
    with pytest.raises(PermissionError, match="登录"):
        connect()
    with pytest.raises(PermissionError, match="登录"):
        submit_task(worker, "Owner missing").result(timeout=10)
    assert not (shared.root / "atlas.db").exists()


def test_real_async_pdf_job_parses_inside_the_uploading_users_workspace(shared, monkeypatch):
    import app.jobs as jobs

    futures = []

    def submit(fn, *args):
        future = submit_task(fn, *args)
        futures.append(future)
        return future

    monkeypatch.setattr(jobs, "submit_task", submit)
    uploaded = {}
    for name in ("alice", "bob"):
        response = _upload(shared.clients[name], _pdf(name + " real queued paper"))
        assert response.status_code == 202, response.text
        uploaded[name] = response.json()
    for future in futures:
        future.result(timeout=10)
    for name, result in uploaded.items():
        client = shared.clients[name]
        task = client.get(f"/api/learning/tasks/{result['task_id']}").json()
        assert task["status"] == "done", task
        assert client.get(f"/api/papers/{result['uid']}").json()["parse_status"] == "parsed"
        workspace = client.get(f"/api/learning/papers/{result['uid']}").json()
        assert workspace["documents"] and name in workspace["documents"][0]["passages"][0]["text"]
        assert {item['stage']: item['status'] for item in workspace['stages']} == {
            'file': 'done', 'parse': 'done', 'graph': 'skipped', 'index': 'skipped',
        }
        assert client.get('/api/system/tasks').json()['items'][0]['warnings'] == []
        other = shared.clients["bob" if name == "alice" else "alice"]
        assert other.get(f"/api/papers/{result['uid']}/file").status_code == 404
    assert not (shared.root / "atlas.db").exists()


def test_disabled_account_stops_running_worker_at_next_checkpoint(shared):
    from app.task_control import TaskStopped, checkpoint, task_scope

    started, resume = Event(), Event()

    def worker():
        with closing(connect()) as conn, task_scope("legacy:1"):
            checkpoint(conn, "before-disable", 0.1)
            started.set()
            assert resume.wait(10)
            checkpoint(conn, "after-disable", 0.9)
            conn.execute("INSERT INTO papers(uid,title) VALUES('must-not-save','Forbidden')")
            conn.commit()

    with user_scope(shared.users["alice"]):
        future = submit_task(worker)
    try:
        assert started.wait(10)
        disabled = shared.clients["admin"].patch(f"/api/auth/users/{shared.users['alice']['id']}", json={"disabled": True})
        assert disabled.status_code == 200
        assert shared.clients["alice"].get("/api/papers").status_code == 401
    finally:
        resume.set()
    with pytest.raises(TaskStopped, match="账号已停用"):
        future.result(timeout=10)
    with user_scope(shared.users["alice"]), closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 0
        assert conn.execute("SELECT phase FROM task_controls").fetchone()[0] == "before-disable"


def test_multiuser_disables_paid_models_and_remote_fetch_but_allows_local_graph(shared):
    from app.db.neo4j_client import get_driver
    from app.llm.client import embed
    from app.research.model_runtime import ResearchModelError, structured_chat

    assert shared.settings.dashscope_api_key == "" and not shared.settings.research_model_enabled
    with pytest.raises(ServiceUnavailable, match="多人模式"):
        get_driver()
    with pytest.raises(RuntimeError, match="not configured"):
        embed(["private user data"])
    with pytest.raises(ResearchModelError, match="model_not_authorized"):
        structured_chat([], schema={}, prompt_version="test", schema_version="test")
    client = shared.clients["alice"]
    local_graph = client.get('/api/graph/nodes')
    assert local_graph.status_code == 200
    assert local_graph.json()['items'] == []
    assert client.post("/api/collect", json={}).status_code == 503
    assert client.post("/api/projects/unavailable-project/sources/link", json={"url": "https://example.org/paper.pdf"}).status_code == 503
    assert client.post("/api/papers/private/fetch-fulltext").status_code == 503
    assert client.post("/api/papers/upload", files={"file": ("paper.pdf", _pdf("Text"), "application/pdf")}).status_code == 409
    runtime = client.get("/api/system/status")
    assert runtime.status_code == 200
    assert runtime.json()["capabilities"]["graph"]
    assert not runtime.json()["capabilities"]["research_model"]
    assert str(shared.root) not in runtime.json()["data_dir"]
    assert "pid" not in runtime.json() and "runtime_id" not in runtime.json()


def test_pdf_page_byte_paper_and_storage_limits_apply_per_user(shared, monkeypatch):
    import app.jobs as jobs

    submitted = []

    def queue(*args):
        future = Future()
        submitted.append(future)
        return future

    monkeypatch.setattr(jobs, "submit_task", queue)
    client = shared.clients["alice"]
    shared.settings.user_pdf_max_pages = 1
    try:
        assert _upload(client, _pdf("Too many pages", pages=2)).status_code == 413
        shared.settings.user_pdf_max_bytes = 1024
        assert _upload(client, b"%PDF-" + b"x" * 1024).status_code == 413
        # Reject oversized request bodies before FastAPI spools the multipart file.
        assert _upload(client, b"%PDF-" + b"x" * (1024 + 65536)).status_code == 413
        shared.settings.user_pdf_max_bytes = 5 * 1024 * 1024
        shared.settings.user_max_papers = 1
        first = _upload(client, _pdf("First accepted paper"))
        assert first.status_code == 202, first.text
        duplicate = _upload(client, (shared.root / "users" / shared.users["alice"]["id"] / "pdfs" / f"{first.json()['uid']}.pdf").read_bytes())
        assert duplicate.status_code == 202 and duplicate.json()["task_id"] == first.json()["task_id"]
        assert _upload(client, _pdf("Second paper exceeds count")).status_code == 409
        assert _upload(shared.clients["bob"], _pdf("Bob independent quota")).status_code == 202
        shared.settings.user_max_papers = 20
        shared.settings.user_storage_max_bytes = 1024 * 1024
        padded_pdf = _pdf("Exceeds remaining file storage") + b"\n%" + b"x" * (1024 * 1024)
        assert _upload(client, padded_pdf).status_code == 413
        assert len(list((shared.root / "users" / shared.users["alice"]["id"] / "pdfs").glob("*.pdf"))) == 1
    finally:
        for future in submitted:
            future.cancel()
