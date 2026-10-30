"""Offline assistant rules, optimistic concurrency, resources and history."""
import hashlib
import importlib.util
import json
import asyncio
from contextlib import closing
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


def test_impact_chain_marks_execution_without_rewriting_history(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    baseline = client.get(f"/api/projects/{pid}/impact").json()
    assert baseline["contract_version"] == "project-impact-v1"
    with connect() as conn:
        conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                     ("changed source text", fixture_project["document_id"]))
        conn.commit()
    changed = client.get(f"/api/projects/{pid}/impact").json()
    assert changed["input_fingerprint"] != baseline["input_fingerprint"]
    affected = next(issue for issue in changed["issues"] if issue["code"] == "quote_mismatch")
    assert {item["kind"] for item in affected["affected"]} >= {"snapshot", "activity"}
    tasks = client.get("/api/workflow/v1/activities", params={"source_kind": "project", "project_id": pid}).json()["items"]
    assert any(task["status"] == "needs_review" for task in tasks)
    assert any(item["kind"] == "source_review" for item in
               client.get("/api/workflow/v1/recommendations").json()["items"])
    with connect() as conn:
        assert conn.execute("SELECT review_status FROM research_snapshots WHERE snapshot_id=?",
                            (fixture_project["snapshot_id"],)).fetchone()[0] == "current"
    assert client.get("/api/projects/absent/impact").status_code == 404


def test_recommendations_rank_current_actions_and_keep_history(fixture_project):
    client = TestClient(app)
    url = "/api/workflow/v1/recommendations"
    before = client.get(url).json()
    assert before["ranking_rule_version"] == "workflow-priority-1"
    assert before["truncated"] is False
    assert any(item["kind"] == "continue_activity" for item in before["items"])
    assert [item["rank"] for item in before["items"]] == list(range(1, len(before["items"]) + 1))
    assert [item["priority_score"] for item in before["items"]] == sorted(
        (item["priority_score"] for item in before["items"]), reverse=True)
    assert all(item["priority_reason"] and item["source_ids"] and item["url"] for item in before["items"])
    assert client.get(url).json() == before

    with connect() as conn:
        conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                     ("changed source text", fixture_project["document_id"]))
        conn.commit()
    after = client.get(url).json()
    assert after["input_fingerprint"] != before["input_fingerprint"]
    assert after["items"][0]["kind"] == "source_review"
    related = [item for item in after["items"] if item["kind"] == "source_review"
               and item["id"].endswith(fixture_project["snapshot_id"])]
    assert len(related) == 1
    assert related[0]["related_activity_count"] >= 1
    with connect() as conn:
        assert conn.execute("SELECT review_status FROM research_snapshots WHERE snapshot_id=?",
                            (fixture_project["snapshot_id"],)).fetchone()[0] == "current"


def test_dependency_index_backfill_and_impact_checkpoint_diff(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    source = {"source_kind": "evidence", "source_id": fixture_project["evidence_id"]}
    url = f"/api/projects/{pid}/dependencies"
    indexed = client.get(url, params=source).json()["targets"]
    assert {item["target_kind"] for item in indexed} == {"plan", "snapshot"}
    assert {item["target_id"] for item in indexed} >= {
        fixture_project["plan_id"], fixture_project["snapshot_id"]}
    assert client.get(url, params={"source_kind": "evidence", "source_id": "unrelated"}).json()["targets"] == []
    assert client.get("/api/projects/absent/dependencies", params=source).status_code == 404
    with connect() as conn:
        evidence = json.loads(conn.execute("SELECT payload_json FROM research_evidence WHERE evidence_id=?",
                                           (fixture_project["evidence_id"],)).fetchone()[0])
    document_source = {"source_kind": "document", "source_id": fixture_project["document_id"],
                       "source_version": evidence["document_version"]}
    exact = client.get(url, params=document_source).json()["targets"]
    assert exact and all(target["source_version"] == evidence["document_version"] for target in exact)
    assert client.get(url, params={**document_source, "source_version": "outdated"}).json()["targets"] == []

    with connect() as conn:
        conn.execute("DELETE FROM research_dependency_edges")
        conn.execute("DELETE FROM research_dependency_index_meta")
        conn.execute("INSERT INTO research_dependency_index_meta(version) VALUES(1)")
        conn.commit()
        store.init_research_schema(conn)
        assert conn.execute("SELECT version FROM research_dependency_index_meta").fetchone()[0] == 2
        store.init_research_schema(conn)
    assert client.get(url, params=source).json()["targets"] == indexed

    baseline = client.get(f"/api/projects/{pid}/audit").json()
    checkpoint_url = f"/api/projects/{pid}/impact/checkpoints"
    assert client.get(checkpoint_url).json()["checkpoint"] is None
    assert client.post(checkpoint_url, json={"expected_fingerprint": "0" * 64}).status_code == 409
    saved = client.post(checkpoint_url, json={"expected_fingerprint": baseline["input_fingerprint"]})
    assert saved.status_code == 200, saved.text
    checkpoint = saved.json()
    assert client.post(checkpoint_url, json={"expected_fingerprint": baseline["input_fingerprint"]}).json() == checkpoint
    assert client.get(checkpoint_url).json()["checkpoint"] == checkpoint
    changes_url = f"/api/projects/{pid}/impact/changes"
    assert client.get(changes_url, params={"checkpoint_id": checkpoint["checkpoint_id"]}).json()["added"] == []

    with connect() as conn:
        original_passage = conn.execute("SELECT text FROM passages WHERE document_id=? LIMIT 1",
                                        (fixture_project["document_id"],)).fetchone()[0]
        conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                     ("changed source text", fixture_project["document_id"]))
        conn.commit()
    changed = client.get(changes_url, params={"checkpoint_id": checkpoint["checkpoint_id"]}).json()
    assert changed["current_fingerprint"] != changed["baseline_fingerprint"]
    assert any(issue["code"] == "quote_mismatch" and fixture_project["snapshot_id"]
               in issue["affected_snapshot_ids"] for issue in changed["added"])
    assert client.post(checkpoint_url, json={"expected_fingerprint": baseline["input_fingerprint"]}).status_code == 409
    assert client.get(changes_url, params={"checkpoint_id": "absent"}).status_code == 404
    assert client.get("/api/projects/absent/impact/changes",
                      params={"checkpoint_id": checkpoint["checkpoint_id"]}).status_code == 404
    mismatch_checkpoint = client.post(checkpoint_url, json={"expected_fingerprint": changed["current_fingerprint"]}).json()
    with connect() as conn:
        conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                     (original_passage, fixture_project["document_id"]))
        conn.commit()
    resolved = client.get(changes_url, params={"checkpoint_id": mismatch_checkpoint["checkpoint_id"]}).json()
    assert any(issue["code"] == "quote_mismatch" for issue in resolved["resolved"])
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM research_impact_checkpoints WHERE project_id=?", (pid,)).fetchone()[0] == 2


def test_readiness_separates_missing_and_conflicting_conditions(fixture_project):
    client = TestClient(app)
    pid = fixture_project["project_id"]
    url = f"/api/projects/{pid}/comparison-readiness"
    baseline = client.get(url).json()
    assert baseline["contract_version"] == "comparison-readiness-v1"
    assert baseline["total_pairs"] >= 1
    with connect() as conn:
        row = conn.execute("SELECT version,payload_json FROM research_fact_versions "
                           "WHERE fact_id=? ORDER BY version DESC LIMIT 1", ("setting-synthetic-b",)).fetchone()
        payload = json.loads(row["payload_json"])
        payload["split"] = "different-split"
        conn.execute("UPDATE research_fact_versions SET payload_json=? WHERE fact_id=? AND version=?",
                     (json.dumps(payload), "setting-synthetic-b", row["version"]))
        conn.commit()
    changed = client.get(url).json()
    assert changed["input_fingerprint"] != baseline["input_fingerprint"]
    assert any(pair["status"] == "conflict" and "split" in pair["conflicting_fields"]
               for pair in changed["pairs"])
    with connect() as conn:
        payload["split"] = None
        conn.execute("UPDATE research_fact_versions SET payload_json=? WHERE fact_id=? AND version=?",
                     (json.dumps(payload), "setting-synthetic-b", row["version"]))
        conn.commit()
    missing = client.get(url).json()
    assert any("split" in pair["missing_fields"] for pair in missing["pairs"])
    assert client.get("/api/projects/absent/comparison-readiness").status_code == 404


def test_readiness_requires_aligned_versions_metrics_and_intact_sources(fixture_project):
    client = TestClient(app)
    url = f"/api/projects/{fixture_project['project_id']}/comparison-readiness"

    def edit_fact(identity, **updates):
        with connect() as conn:
            row = conn.execute("SELECT version,payload_json FROM research_fact_versions "
                               "WHERE fact_id=? ORDER BY version DESC LIMIT 1", (identity,)).fetchone()
            payload = json.loads(row["payload_json"])
            payload.update(updates)
            conn.execute("UPDATE research_fact_versions SET payload_json=? WHERE fact_id=? AND version=?",
                         (json.dumps(payload), identity, row["version"]))
            conn.commit()

    with connect() as conn:
        setting_a = json.loads(conn.execute("SELECT payload_json FROM research_fact_versions "
                                            "WHERE fact_id='setting-synthetic-a' ORDER BY version DESC LIMIT 1").fetchone()[0])
        metric_a = json.loads(conn.execute("SELECT payload_json FROM research_fact_versions "
                                           "WHERE fact_id='measurement-synthetic-a' ORDER BY version DESC LIMIT 1").fetchone()[0])
        metric_b = json.loads(conn.execute("SELECT payload_json FROM research_fact_versions "
                                           "WHERE fact_id='measurement-synthetic-b' ORDER BY version DESC LIMIT 1").fetchone()[0])
    edit_fact("setting-synthetic-b", split=setting_a["split"],
              evaluation_protocol=setting_a["evaluation_protocol"])
    edit_fact("measurement-synthetic-b", metric_scope=metric_a["metric_scope"])
    aligned = client.get(url).json()["pairs"][0]
    assert aligned["status"] == "comparable"
    assert aligned["shared_metrics"][0]["left_measurement_id"] == "measurement-synthetic-a"
    assert {check["field"] for check in aligned["condition_checks"]} >= {
        "dataset", "dataset_version", "split", "evaluation_protocol"}

    edit_fact("measurement-synthetic-b", field_evidence=[field for field in metric_b["field_evidence"]
                                                         if field["field_path"] != "metric_scope"])
    unbound = client.get(url).json()["pairs"][0]
    assert unbound["status"] == "information_insufficient"
    assert "measurement-synthetic-b.metric_scope" in unbound["evidence_gaps"]
    edit_fact("measurement-synthetic-b", field_evidence=metric_b["field_evidence"])

    edit_fact("setting-synthetic-b", dataset_version="new-version")
    version_conflict = client.get(url).json()["pairs"][0]
    assert version_conflict["status"] == "conflict"
    assert "dataset_version" in version_conflict["conflicting_fields"]
    edit_fact("setting-synthetic-b", dataset_version=setting_a["dataset_version"], subset="named-subset")
    subset_gap = client.get(url).json()["pairs"][0]
    assert subset_gap["status"] == "information_insufficient"
    assert "subset" in subset_gap["missing_fields"]
    edit_fact("setting-synthetic-b", subset=None, preprocessing=["normalize"])
    assert "preprocessing" in client.get(url).json()["pairs"][0]["missing_fields"]
    edit_fact("setting-synthetic-b", preprocessing=[])

    edit_fact("measurement-synthetic-b", aggregation="macro")
    aggregation_gap = client.get(url).json()["pairs"][0]
    assert aggregation_gap["status"] == "information_insufficient"
    assert "metric_aggregation" in aggregation_gap["missing_fields"]
    edit_fact("measurement-synthetic-b", aggregation=None, sample_size=100)
    size_gap = client.get(url).json()["pairs"][0]
    assert "sample_size" in size_gap["missing_fields"]
    edit_fact("measurement-synthetic-b", sample_size=None)

    with connect() as conn:
        conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                     ("changed source text", fixture_project["document_id"]))
        conn.commit()
    source_gap = client.get(url).json()["pairs"][0]
    assert source_gap["status"] == "information_insufficient"
    assert "quote_mismatch" in source_gap["source_gaps"]


def test_failed_practice_recommends_review_without_mastery():
    client = TestClient(app)
    base = "/api/cases/diffusion-policy-intro/sessions"
    session = client.post(base).json()
    exercise = client.get(f"{base}/{session['id']}/coach").json()["exercises"][0]
    response = client.post(f"{base}/{session['id']}/practice/{exercise['id']}/answers",
                           json={"version": 0, "shape": [99, 99, 99]})
    assert response.status_code == 200
    suggestions = client.get("/api/workflow/v1/recommendations").json()
    reviews = [item for item in suggestions["items"] if item["kind"] == "practice_review"]
    assert reviews and reviews[0]["priority_score"] == 80
    assert f"session={session['id']}" in reviews[0]["url"]
    assert client.get("/api/workflow/v1/mastery").json()["items"] == []
    answer = [exercise["parameters"][key] for key in ("B", "To", "Do")]
    assert client.post(f"{base}/{session['id']}/practice/{exercise['id']}/answers",
                       json={"version": 1, "shape": answer}).status_code == 200
    resolved = client.get("/api/workflow/v1/recommendations").json()
    assert not any(item["kind"] == "practice_review" for item in resolved["items"])
    assert client.get("/api/workflow/v1/mastery").json()["items"] == []


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
        from app.knowledge.unified import sync_legacy
        sync_legacy(conn, kid=created[0])
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


@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_versioned_pdf_response_sends_verified_bytes_even_if_file_changes_before_send(mutation):
    import pymupdf
    from app.api.assistant import versioned_file
    from app.tenancy import data_dir

    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Original verified document version")
        original = pdf.tobytes()
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES('version-race','Versioned source')")
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,'fulltext')",
                     ("document-race", "version-race", hashlib.sha256(original).hexdigest()))
        conn.commit()
    folder = data_dir() / "pdfs"
    folder.mkdir(exist_ok=True)
    path = folder / "version-race.pdf"
    path.write_bytes(original)
    response = versioned_file("version-race", "document-race")
    # Mutation occurs after the endpoint's hash check but before ASGI sends
    # its response. Reopening the pathname here would expose another version.
    if mutation == "replace":
        path.write_bytes(original + b"\n% replacement after verification")
    else:
        path.unlink()
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "headers": [], "path": "/", "extensions": {},
             "asgi": {"version": "3.0", "spec_version": "2.4"}}
    asyncio.run(response(scope, receive, send))
    assert messages[0]["status"] == 200
    assert response.headers["content-disposition"] == "inline"
    assert response.headers["content-type"] == "application/pdf"
    assert b"".join(message.get("body", b"") for message in messages) == original
    subsequent = TestClient(app).get("/api/papers/version-race/documents/document-race/file")
    assert subsequent.status_code == (409 if mutation == "replace" else 404)


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
