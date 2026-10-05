import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect, reset_running_tasks
from app.models.paper import ParsedPaper, Section
from app.db.workspace import save_document, document_view
from tests.test_evidence_workspace import seed


def test_atomic_original_deduplicates_and_does_not_overwrite(tmp_path):
    from app.storage import save_original

    path = tmp_path / "a.pdf"
    save_original(path, b"%PDF-first")
    save_original(path, b"%PDF-first")
    with pytest.raises(ValueError):
        save_original(path, b"%PDF-other")
    assert path.read_bytes() == b"%PDF-first"
    assert not list(tmp_path.glob("*.tmp"))


def test_table_context_is_preserved_and_not_automatically_claimed(monkeypatch):
    from app.pipeline.evidence import extract_document

    conn = connect(":memory:")
    paper = seed(conn)
    save_document(
        conn,
        "p1",
        ParsedPaper(
            uid="p1",
            title="Test",
            abstract="",
            sections=[
                Section(
                    heading="Results",
                    text="Metric | Setting\n90 | only condition A",
                    kind="table",
                    metadata={
                        "rows": [["Metric", "Setting"], ["90", "only condition A"]],
                        "caption": "Restricted experiment",
                    },
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "app.pipeline.evidence.chat",
        lambda *a, **k: pytest.fail("table must not enter automatic claim extraction"),
    )
    result = extract_document(conn, paper)
    assert result["relations"] == 0
    table = document_view(conn, "p1")[0]["passages"][0]
    assert json.loads(table["metadata_json"])["caption"] == "Restricted experiment"


def test_curated_source_is_candidate_until_explicit_review(monkeypatch):
    client = TestClient(app)
    request = {
        "title": "Synthetic teaching source",
        "source_url": "https://example.org/synthetic",
        "text": "First understand A before B.",
        "rel_type": "PREREQUISITE_OF",
        "src_name": "A",
        "src_type": "concept",
        "dst_name": "B",
        "dst_type": "concept",
        "quote": "understand A before B",
        "actor": "test maintainer",
    }
    response = client.post("/api/learning/sources", json=request)
    assert response.status_code == 201
    kid = response.json()["id"]
    assert (
        client.get("/api/learning/quality").json()["items"][0]["status"] == "candidate"
    )
    monkeypatch.setattr("app.api.review._approve_relation", lambda *a: None)
    monkeypatch.setattr("app.graphsvc.entities.set_relation_quality", lambda *a: None)
    response = client.post(
        f"/api/learning/quality/{kid}",
        json={"action": "verify", "actor": "reviewer", "reason": "read context"},
    )
    assert response.status_code == 200
    assert (
        client.get("/api/learning/quality").json()["items"][0]["status"]
        == "human_verified"
    )


def test_queue_deduplication_and_restart_recovery(monkeypatch):
    import app.jobs as jobs

    submitted = []
    monkeypatch.setattr(jobs, "submit_task", lambda *a: submitted.append(a))
    tid = jobs.enqueue("guide", {"uid": "p1"})
    try:
        assert jobs.enqueue("guide", {"uid": "p1"}) == tid
        assert len(submitted) == 1
        conn = connect()
        assert reset_running_tasks(conn) == 1
        assert (
            conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0]
            == "failed"
        )
        conn.close()
    finally:
        jobs._slots.release()


def test_download_rejects_unsupported_host_before_http(monkeypatch):
    from app.fulltext import fetch_pdf

    conn = connect()
    seed(conn)
    conn.execute("UPDATE papers SET pdf_url='https://127.0.0.1/private'")
    conn.commit()
    with pytest.raises(ValueError, match="Unsupported PDF host"):
        fetch_pdf(conn, "p1")
    assert (
        conn.execute(
            "SELECT status FROM pipeline_stages WHERE stage='download'"
        ).fetchone()[0]
        == "failed"
    )
    conn.close()


def test_human_evaluation_rejects_unlabelled_data_and_leakage():
    from scripts.evaluate_quality import evaluate

    with pytest.raises(ValueError):
        evaluate([{"sample_key": "empty"}])
    row = {
        "sample_key": "1",
        "split": "test",
        "relation_type": "USES",
        "expected": True,
        "predicted": True,
        "evidence_supported": True,
        "annotator": "human",
        "source": "source",
    }
    with pytest.raises(ValueError, match="duplicate"):
        evaluate([row, {**row, "split": "development"}])
    report = evaluate([row])
    assert report["by_relation"]["USES"]["precision"] == 1
    assert report["by_relation"]["USES"]["precision_wilson_95"][0] < 0.95
    assert report["by_relation"]["USES"]["automatic_publication_enabled"] is False


def test_protocol_status_is_only_published_with_maintainer_attestation():
    conn = connect()
    seed(conn)
    save_document(
        conn, "p1", ParsedPaper(uid="p1", title="t", abstract="synthetic source")
    )
    pid = document_view(conn, "p1")[0]["passages"][0]["id"]
    conn.close()
    body = {
        "scope": "example",
        "repository": "https://example.org/synthetic",
        "commit": "abc",
        "environment": "test-only",
        "resources": "test-only",
        "steps": [
            {
                "title": "example",
                "inputs": "a",
                "operation": "b",
                "expected_output": "c",
                "acceptance": "d",
                "troubleshooting": "e",
            }
        ],
        "evidence_ids": [pid],
        "maintainer": "human",
        "tested_at": "2026-09-30",
        "test_log": "synthetic fixture, not a real reproduction",
        "verified": False,
    }
    client = TestClient(app)
    assert client.put("/api/learning/papers/p1/protocol", json=body).status_code == 200
    assert client.get("/api/learning/papers/p1").json()["protocol"] is None
    assert (
        client.put(
            "/api/learning/papers/p1/protocol", json={**body, "verified": True}
        ).status_code
        == 200
    )
    response = client.get("/api/learning/papers/p1").json()
    assert response["reproduction"]["verified"] is True
    assert response["protocol"]["scope"] == "example"


def test_partial_success_job_can_be_retried(monkeypatch):
    conn = connect()
    tid = conn.execute(
        "INSERT INTO tasks(type,params_json,status,result_json) VALUES('ingest',?,'done',?)",
        (
            json.dumps({"uid": "p1"}),
            json.dumps({"warnings": [{"stage": "index", "error": "offline"}]}),
        ),
    ).lastrowid
    conn.commit()
    conn.close()
    calls = []
    monkeypatch.setattr(
        "app.jobs.enqueue", lambda kind, params: calls.append((kind, params)) or 99
    )
    response = TestClient(app).post(f"/api/learning/tasks/{tid}/retry")
    assert response.status_code == 202 and response.json()["task_id"] == 99
    assert calls == [("ingest", {"uid": "p1"})]
