"""Offline assistant rules, optimistic concurrency, resources and history."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect
from app.db import projects as store
from app.models.research import ComputeConstraint, NamedValue, NumericValue, ResearchProjectPatch
from app.models.research import PlanSaveRequest
from app.research.constraints import evaluate_constraints
from tests.test_research_t3_comparison import image_bundle, project


@pytest.fixture
def fixture_project(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "evaluation/research_atlas/prepare_browser_fixture.py"
    spec = importlib.util.spec_from_file_location("assistant_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    directory = tmp_path / "assistant"
    manifest = module.prepare_fixture(directory)
    monkeypatch.setenv("DATA_DIR", str(directory))
    from app.config import get_settings
    get_settings.cache_clear()
    return manifest


def test_scenarios_fingerprint_and_no_writes(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    before = client.get(f"/api/projects/{pid}").json()
    insights = client.get(f"/api/projects/{pid}/insights").json()
    assert insights["contract_version"] == "assistant-v1"
    constraints = before["constraints"]
    constraints["compute"] = [{"memory": {"value": 8, "unit": "GB"}, "device_count": 1}]
    body = {"expected_project_version": before["version"], "input_fingerprint": insights["input_fingerprint"],
            "scenarios": [{"id": str(i), "label": f"Case {i}", "constraints": constraints} for i in range(4)]}
    result = client.post(f"/api/projects/{pid}/scenarios/evaluate", json=body)
    assert result.status_code == 200, result.text
    assert len(result.json()["scenarios"]) == 4
    assert any(c["status"] == "unknown" for c in result.json()["scenarios"][0]["candidates"][0]["checks"])
    assert client.get(f"/api/projects/{pid}").json()["constraints"] != constraints
    assert client.get(f"/api/projects/{pid}/insights").json() == insights
    body["input_fingerprint"] = "stale"
    assert client.post(f"/api/projects/{pid}/scenarios/evaluate", json=body).status_code == 409
    body["scenarios"].append(body["scenarios"][0])
    assert client.post(f"/api/projects/{pid}/scenarios/evaluate", json=body).status_code == 422
    graph = client.get(f"/api/projects/{pid}/canvas").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert fixture_project["evidence_id"] in ids
    assert all(e["source_id"] in ids and e["target_id"] in ids for e in graph["edges"])


def test_project_audit_detects_quote_breakage_and_affected_snapshots(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    url = f"/api/projects/{pid}/audit"
    baseline = client.get(url)
    assert baseline.status_code == 200, baseline.text
    original = baseline.json()
    assert original["contract_version"] == "project-audit-v1"
    assert original["summary"]["blocking"] == 0
    assert client.get(url).json() == original
    with connect() as conn:
        conn.execute("UPDATE passages SET text=? WHERE document_id=?", ("changed source text", fixture_project["document_id"]))
        conn.commit()
    changed = client.get(url).json()
    assert changed["input_fingerprint"] != original["input_fingerprint"]
    mismatches = [issue for issue in changed["issues"] if issue["code"] == "quote_mismatch"]
    assert mismatches
    assert fixture_project["snapshot_id"] in mismatches[0]["affected_snapshot_ids"]
    assert client.get(f"/api/projects/{pid}").status_code == 200


def test_project_audit_finds_version_and_incompatible_conditions(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    with connect() as conn:
        row = conn.execute(
            "SELECT version,payload_json FROM research_fact_versions WHERE fact_id=? ORDER BY version DESC LIMIT 1",
            ("measurement-synthetic-b",),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["metric_scope"] = "image/browser_fixture_only"
        conn.execute(
            "UPDATE research_fact_versions SET payload_json=? WHERE fact_id=? AND version=?",
            (json.dumps(payload, ensure_ascii=False), "measurement-synthetic-b", row["version"]),
        )
        conn.execute("UPDATE documents SET content_hash=? WHERE id=?", ("changed-hash", fixture_project["document_id"]))
        conn.commit()
    response = client.get(f"/api/projects/{pid}/audit")
    assert response.status_code == 200, response.text
    codes = {issue["code"] for issue in response.json()["issues"]}
    assert {"source_version_unavailable", "evidence_version_mismatch", "incompatible_conditions"} <= codes
    assert client.get("/api/projects/absent/audit").status_code == 404


def test_relation_audit_keeps_candidates_unpublished_and_detects_cycle(fixture_project):
    client = TestClient(app)
    created = []
    for index, (src, dst) in enumerate((("Concept A", "Concept B"), ("Concept B", "Concept A"))):
        response = client.post("/api/learning/sources", json={
            "title": f"Synthetic teaching source {index}",
            "source_url": f"https://example.test/teaching-{index}",
            "text": f"In this synthetic exercise, {src} precedes {dst}.",
            "quote": f"{src} precedes {dst}",
            "rel_type": "PREREQUISITE_OF", "src_name": src, "src_type": "concept",
            "dst_name": dst, "dst_type": "concept", "actor": "synthetic-test",
        })
        assert response.status_code == 201, response.text
        created.append(response.json()["id"])
    report = client.get("/api/learning/relations/audit")
    assert report.status_code == 200, report.text
    value = report.json()
    assert value["contract_version"] == "relation-audit-v1"
    assert any(issue["code"] == "prerequisite_cycle"
               and set(issue["relation_ids"]) == set(created) for issue in value["issues"])
    with connect() as conn:
        assert {conn.execute("SELECT status FROM knowledge WHERE id=?", (rid,)).fetchone()[0]
                for rid in created} == {"candidate"}
        conn.execute("UPDATE knowledge SET quote=? WHERE id=?", ("tampered", created[0]))
        conn.commit()
    changed = client.get("/api/learning/relations/audit").json()
    assert changed["input_fingerprint"] != value["input_fingerprint"]
    assert any(issue["code"] == "quote_mismatch" and created[0] in issue["relation_ids"]
               for issue in changed["issues"])


def test_local_radar_links_new_library_paper_to_affected_plan(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    url = f"/api/projects/{pid}/radar"
    before = client.get(url).json()
    assert before["items"] == []
    with connect() as conn:
        conn.execute(
            "INSERT INTO papers(uid,title,abstract,authors_json,categories_json,source) "
            "VALUES(?,?,?,?,?,?)",
            ("new-synthetic-method", "SyntheticProbe replication note", "SyntheticAD-Fixture",
             "[]", "[]", "fixture"),
        )
        conn.commit()
    after = client.get(url).json()
    assert after["input_fingerprint"] != before["input_fingerprint"]
    assert after["items"][0]["uid"] == "new-synthetic-method"
    assert fixture_project["plan_id"] in after["items"][0]["potentially_affected_plan_ids"]
    assert client.get("/api/projects/absent/radar").status_code == 404


def test_project_audit_reports_incomplete_protocol_without_mutating_saved_plan(fixture_project):
    pid = fixture_project["project_id"]
    with connect() as conn:
        row = conn.execute(
            "SELECT version,payload_json FROM research_plan_versions WHERE plan_id=? ORDER BY version DESC LIMIT 1",
            (fixture_project["plan_id"],),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["steps"][0]["acceptance_criteria"] = []
        payload["steps"][0]["evidence_ids"] = ["absent-evidence"]
        conn.execute(
            "UPDATE research_plan_versions SET payload_json=? WHERE plan_id=? AND version=?",
            (json.dumps(payload, ensure_ascii=False), fixture_project["plan_id"], row["version"]),
        )
        conn.commit()
    report = TestClient(app).get(f"/api/projects/{pid}/audit").json()
    issues = {issue["code"]: issue for issue in report["issues"]}
    assert {"plan_step_gap", "plan_step_evidence_missing"} <= issues.keys()
    assert fixture_project["plan_id"] in issues["plan_step_gap"]["affected_plan_ids"]
    assert issues["plan_step_evidence_missing"]["severity"] == "blocking"
    with connect() as conn:
        assert json.loads(conn.execute(
            "SELECT payload_json FROM research_plan_versions WHERE plan_id=? AND version=?",
            (fixture_project["plan_id"], row["version"]),
        ).fetchone()[0]) == payload


def test_resource_units_and_complete_device_alternatives():
    bundle = image_bundle()
    setting = bundle.experiment_settings[0]
    setting.resources = [NamedValue(name="device_kind", value="GPU"), NamedValue(name="device_count", value=2),
                         NamedValue(name="vram", value=16000, unit="MB"), NamedValue(name="cost", value=5, unit="USD")]
    p = project(compute=[ComputeConstraint(device_kind="CPU", device_count=4, memory=NumericValue(value=64, unit="GB")),
                         ComputeConstraint(device_kind="GPU", device_count=1, memory=NumericValue(value=24, unit="GB"))])
    p.constraints.cost_budget = NumericValue(value=100, unit="CNY")
    checks = evaluate_constraints(p, bundle.methods, [setting], bundle.measurements)[0]
    assert checks.status == "conflict"  # cannot combine CPU count with GPU type
    assert next(c for c in checks.checks if c.dimension == "cost_budget").status == "unknown"
    p.constraints.compute = [ComputeConstraint(device_kind="GPU", device_count=2, memory=NumericValue(value=16, unit="GB"))]
    checks = evaluate_constraints(p, bundle.methods, [setting], bundle.measurements)[0]
    assert next(c for c in checks.checks if c.dimension == "memory").status == "match"
    setting.resources = []
    assert evaluate_constraints(p, bundle.methods, [setting], bundle.measurements)[0].status == "unknown"


def test_practice_server_grades_retries_and_conflict():
    client = TestClient(app)
    base = "/api/cases/diffusion-policy-intro/sessions"
    session = client.post(base).json()
    url = f"{base}/{session['id']}"
    assert session["state"]["practice"] == {}
    coach = client.get(url + "/coach").json()
    ex = coach["exercises"][0]
    assert ex["result"] is None and "expected" not in ex
    answer = [ex["parameters"][k] for k in ["B", "To", "Do"]]
    grade_url = url + f"/practice/{ex['id']}/answers"
    first = client.post(grade_url, json={"version": 0, "shape": answer}).json()
    assert first["state"]["practice"][ex["id"]]["correct"] is True
    assert first["state"]["answers"] == {} and first["state"]["read_steps"] == []
    assert client.post(grade_url, json={"version": 0, "shape": answer}).status_code == 409
    repeat = client.post(grade_url, json={"version": 1, "shape": answer}).json()
    assert repeat["state"]["practice"][ex["id"]]["attempts"] == 1
    assert len(repeat["state"]["practice_history"]) == 1
    updated = client.get(url + "/coach").json()
    assert updated["coverage"]["practice_correct"] == 1
    assert ex["id"] not in {a["id"] for a in updated["actions"]}
    assert client.post(grade_url, json={"version": 2, "shape": [True, 3, 20]}).status_code == 422
    assert client.post(url + "/practice/unknown/answers", json={"version": 2, "choice": 0}).status_code == 422


def test_pdf_version_guard_and_snapshot_history(fixture_project):
    client = TestClient(app)
    pid, uid, doc = (fixture_project[k] for k in ["project_id", "paper_uid", "document_id"])
    resources = client.get("/api/resources", params={"scope": "project", "id": pid}).json()
    pdf = next(r for r in resources["items"] if r["id"] == doc)
    assert pdf["origin"] == "literature"
    assert client.get(pdf["url"]).status_code == 404
    from app.config import get_settings
    path = Path(get_settings().data_dir) / "pdfs" / f"{uid}.pdf"
    path.parent.mkdir()
    path.write_bytes(b"invalid PDF bytes")
    assert client.get(pdf["url"]).status_code == 409
    with connect() as conn:
        conn.execute("UPDATE documents SET content_hash=? WHERE id=?", (hashlib.sha256(path.read_bytes()).hexdigest(), doc))
        conn.commit()
        current = store.get_project(conn, pid)
        store.update_project(conn, pid, ResearchProjectPatch(expected_version=current.version,
                             constraints=current.constraints.model_copy(update={"version": current.constraints.version + 1, "notes": ["new resource scope"]})))
    diff = client.get(f"/api/projects/{pid}/snapshots/{fixture_project['snapshot_id']}/diff")
    assert diff.status_code == 200, diff.text
    assert any(c["path"] == "project.constraints.notes" for c in diff.json()["changes"])
    assert diff.json()["affected"]
    assert client.get(f"/api/projects/{pid}/snapshots/{fixture_project['snapshot_id']}/diff", params={"against": fixture_project["snapshot_id"]}).json()["changes"] == []
    assert client.get(f"/api/projects/{pid}/snapshots/absent/diff").status_code == 404


def test_optional_explain_disabled_does_not_affect_rules(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    report = client.get(f"/api/projects/{pid}/insights").json()
    response = client.post("/api/assistant/explain", json={"scope": "project", "id": pid,
                           "input_fingerprint": report["input_fingerprint"], "action_ids": [report["actions"][0]["id"]]})
    assert response.status_code == 503
    assert client.get(f"/api/projects/{pid}/insights").json() == report


def test_explain_one_call_scoped_output_and_stale_input(fixture_project, monkeypatch):
    from app.research import model_runtime
    client = TestClient(app)
    pid = fixture_project["project_id"]
    report = client.get(f"/api/projects/{pid}/insights").json()
    aid = report["actions"][0]["id"]
    calls = []

    def explain(messages, **kwargs):
        calls.append((messages, kwargs))
        return json.dumps({"explanations": [{"action_id": aid, "text": "先定位当前记录缺失的条件。"}]})

    monkeypatch.setattr(model_runtime, "structured_chat", explain)
    request = {"scope": "project", "id": pid, "input_fingerprint": "stale", "action_ids": [aid]}
    assert client.post("/api/assistant/explain", json=request).status_code == 409
    assert calls == []
    request["input_fingerprint"] = report["input_fingerprint"]
    response = client.post("/api/assistant/explain", json=request)
    assert response.status_code == 200
    assert len(calls) == 1 and response.json()["status"] == "model_suggestion"
    monkeypatch.setattr(model_runtime, "structured_chat", lambda *a, **k: json.dumps({"explanations": [{"action_id": "invented", "text": "Bad"}]}))
    assert client.post("/api/assistant/explain", json=request).status_code == 502
    assert client.get(f"/api/projects/{pid}/insights").json() == report


def test_diff_plan_steps_and_missing_sqlite_history(fixture_project):
    from app.assistant.engine import diff_snapshots
    pid, sid = fixture_project["project_id"], fixture_project["snapshot_id"]
    with connect() as conn:
        plan = store.get_plan(conn, fixture_project["plan_id"])
        project = store.get_project(conn, pid)
        step = plan.steps[0].model_copy(update={"title": "Updated source review"})
        store.save_plan(conn, pid, PlanSaveRequest(expected_project_version=project.version,
                        expected_plan_version=plan.version, plan=plan.model_copy(update={"steps": [step]})))
        diff = diff_snapshots(conn, pid, sid, "current")
        assert any(c["path"] == f"plan.steps.{step.id}.title" for c in diff["changes"])
        assert any(step.id in a["step_ids"] for a in diff["affected"])
        snapshot = store.get_snapshot(conn, pid, sid)
        missing = snapshot.frozen_facts[0]
        conn.execute("DELETE FROM research_fact_versions WHERE fact_id=? AND version=?", (missing.id, missing.version))
        conn.commit()
        assert missing.id in diff_snapshots(conn, pid, sid, "current")["unresolved"]
