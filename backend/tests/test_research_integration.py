"""Mounted-app integration tests with temporary SQLite and mocked external services.

These tests exercise the real project API, task runner, T2 extraction, T3 planning,
and T5 projection assembly.  They are not real-model or real-Neo4j validation.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db.sqlite import connect
from app.main import app
from app.models.research import GraphProjectionResult


def _claim(value, passage_id: str, quote: str):
    return {
        "value": value,
        "finding_status": "reported",
        "evidence": [
            {
                "passage_id": passage_id,
                "document_id": "doc-novel",
                "page": 3,
                "heading": "Synthetic experiment",
                "quote": quote,
            }
        ],
    }


def _model_output():
    method_quote = "We propose NovelProbe."
    quote_a = "On UnknownBench split A, NovelProbe obtains image AUROC 0.91."
    quote_b = "On UnknownBench split B, NovelProbe obtains image AUROC 0.89."

    def setting(local_id: str, name: str, split: str, value: float, quote: str):
        return {
            "local_id": local_id,
            "name": _claim(name, "passage-novel", quote),
            "dataset": _claim("UnknownBench", "passage-novel", quote),
            "split": _claim(split, "passage-novel", quote),
            "measurements": [
                {
                    "local_id": f"measurement-{local_id}",
                    "metric_name": _claim("image AUROC", "passage-novel", quote),
                    "value": {
                        "value": {"value": value, "unit": None, "scale": "fraction"},
                        "finding_status": "reported",
                        "evidence": _claim(value, "passage-novel", quote)["evidence"],
                    },
                }
            ],
        }

    return {
        "methods": [
            {
                "local_id": "novel-method",
                "claim_role": "current_paper_method",
                "name": _claim("NovelProbe", "passage-novel", method_quote),
                "experiment_settings": [
                    setting("setting-a", "UnknownBench split A", "split A", 0.91, quote_a),
                    setting("setting-b", "UnknownBench split B", "split B", 0.89, quote_b),
                ],
            }
        ],
        "warnings": [],
    }


def _poll_task(client: TestClient, task_id: str):
    response = client.get(f"/api/projects/tasks/{task_id}")
    assert response.status_code == 200
    return response.json()


def test_mounted_project_flow_exports_history_and_tracks_impacts(monkeypatch):
    import app.jobs as jobs
    import app.research.graph_projection as graph_projection
    import app.research.service as research_service
    import app.research_extraction.candidates as extraction

    monkeypatch.setattr(jobs, "submit_task", lambda fn, *args: fn(*args))
    monkeypatch.setattr(
        research_service,
        "plan_suggestion_provider",
        lambda value: {"additional_steps": [{
            "title": "人工复核", "purpose": "核对所选来源",
            "procedure": ["检查原文与所选设置，不运行命令"],
            "acceptance_criteria": ["用户确认来源；不确定时停止"],
            "evidence_ids": [value.evidence[0].id],
        }]},
    )
    monkeypatch.setattr(
        extraction,
        "chat",
        lambda messages, json_mode=False: json.dumps(_model_output()),
    )
    monkeypatch.setattr(
        graph_projection,
        "project_graph",
        lambda projection: GraphProjectionResult(
            project_id=projection.project_id,
            snapshot_id=projection.snapshot_id,
            projected_nodes=len(projection.nodes),
            projected_edges=len(projection.edges),
        ),
    )

    passage = (
        "We propose NovelProbe. "
        "On UnknownBench split A, NovelProbe obtains image AUROC 0.91. "
        "On UnknownBench split B, NovelProbe obtains image AUROC 0.89."
    )
    with connect() as conn:
        conn.execute(
            "INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)",
            ("paper-novel", "Previously unseen synthetic paper", "synthetic"),
        )
        conn.execute(
            "INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)",
            ("doc-novel", "paper-novel", "novel-hash", "fulltext"),
        )
        conn.execute(
            "INSERT INTO passages(id,document_id,heading,text,page,ordinal,kind,metadata_json) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                "passage-novel",
                "doc-novel",
                "Synthetic experiment",
                passage,
                3,
                0,
                "text",
                "{}",
            ),
        )
        conn.commit()

    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "Novel material validation",
            "research_question": "Which reported setting should be validated first?",
            "domain": "image_anomaly_detection",
            "constraints": {
                "version": 1,
                "objective": "Run a traceable first validation",
                "required_metrics": ["image AUROC"],
            },
        },
    )
    assert created.status_code == 201
    project = created.json()

    invalid = client.post("/api/projects", json={"title": "missing fields"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "validation_error"

    linked = client.post(
        f"/api/projects/{project['id']}/papers",
        json={
            "expected_project_version": 1,
            "paper_uid": "paper-novel",
            "role": "primary",
            "note": None,
        },
    )
    assert linked.status_code == 201
    link = linked.json()
    assert link["linked_document_id"] == "doc-novel"

    extraction_task = client.post(
        f"/api/projects/{project['id']}/papers/{link['id']}/extractions",
        json={"expected_project_version": 2, "document_id": "doc-novel"},
    )
    assert extraction_task.status_code == 202
    assert _poll_task(client, extraction_task.json()["id"])["status"] == "succeeded"

    facts_response = client.get(f"/api/projects/{project['id']}/facts")
    assert facts_response.status_code == 200
    facts = facts_response.json()
    assert [item["name"] for item in facts["methods"]] == ["NovelProbe"]
    assert {item["split"] for item in facts["experiment_settings"]} == {
        "split A",
        "split B",
    }
    assert all(item["resources"] == [] for item in facts["experiment_settings"])
    assert {item["value"]["value"] for item in facts["measurements"]} == {0.91, 0.89}

    confirmed = {}
    for fact in [
        *facts["methods"],
        *facts["experiment_settings"],
        *facts["measurements"],
    ]:
        response = client.patch(
            f"/api/projects/{project['id']}/facts/{fact['id']}/status",
            json={
                "expected_version": fact["version"],
                "from_status": "candidate",
                "to_status": "user_confirmed",
                "actor": "integration-reviewer",
                "reason": "matched the frozen synthetic passage",
            },
        )
        assert response.status_code == 200
        confirmed[fact["id"]] = response.json()

    method = facts["methods"][0]
    settings = facts["experiment_settings"]
    measurements = facts["measurements"]
    comparison = client.post(
        f"/api/projects/{project['id']}/comparisons",
        json={
            "project_id": project["id"],
            "project_version": 2,
            "domain": "image_anomaly_detection",
            "candidates": [
                {
                    "method_id": method["id"],
                    "experiment_setting_id": setting["id"],
                    "measurement_ids": [
                        item["id"]
                        for item in measurements
                        if item["experiment_setting_id"] == setting["id"]
                    ],
                }
                for setting in settings
            ],
        },
    )
    assert comparison.status_code == 200
    assert any(not group["comparable"] for group in comparison.json()["groups"])

    evidence_id = facts["methods"][0]["field_evidence"][0]["evidence_ids"][0]
    decision_response = client.post(
        f"/api/projects/{project['id']}/decisions",
        json={
            "expected_project_version": 2,
            "selected_method_id": method["id"],
            "selected_experiment_setting_ids": [settings[0]["id"]],
            "considered_candidate_ids": [item["id"] for item in settings],
            "rationale": "User selected split A for the first validation.",
            "evidence_ids": [evidence_id],
        },
    )
    assert decision_response.status_code == 201
    decision = decision_response.json()
    assert decision["source_kind"] == "user_input"

    generated = client.post(
        f"/api/projects/{project['id']}/plans/generate",
        json={
            "expected_project_version": 2,
            "decision_id": decision["id"],
            "decision_version": decision["version"],
        },
    )
    assert generated.status_code == 202
    generated_task = _poll_task(client, generated.json()["id"])
    assert generated_task["status"] == "succeeded"
    draft = generated_task["result"]["plan"]
    assert draft["title"].startswith("[模型建议·待人工确认]")

    draft["id"] = "plan-integration"
    saved_response = client.put(
        f"/api/projects/{project['id']}/plans/plan-integration",
        json={
            "expected_project_version": 2,
            "expected_plan_version": 0,
            "plan": draft,
        },
    )
    assert saved_response.status_code == 200
    saved = saved_response.json()
    assert saved["status"] == "saved"

    snapshot_response = client.post(
        f"/api/projects/{project['id']}/snapshots",
        json={
            "expected_project_version": 2,
            "plan_id": saved["id"],
            "plan_version": saved["version"],
        },
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()
    status = client.get(
        f"/api/projects/{project['id']}/snapshots/{snapshot['id']}/projection"
    ).json()
    assert status["status"] == "succeeded" and status["task_id"]

    exported = client.get(
        f"/api/projects/{project['id']}/snapshots/{snapshot['id']}/export",
        params={"format": "json"},
    )
    assert exported.status_code == 200
    exported_json = exported.json()
    assert exported_json["frozen_documents"][0]["content_hash"] == "novel-hash"
    assert exported_json["frozen_facts"]
    markdown = client.get(
        f"/api/projects/{project['id']}/snapshots/{snapshot['id']}/export",
        params={"format": "markdown"},
    )
    assert markdown.status_code == 200
    assert "## 未知项" in markdown.text and "## 冻结来源" in markdown.text

    def fail_projection(_projection):
        raise RuntimeError("synthetic graph unavailable")

    monkeypatch.setattr(graph_projection, "project_graph", fail_projection)
    failed_snapshot_response = client.post(
        f"/api/projects/{project['id']}/snapshots",
        json={
            "expected_project_version": 2,
            "plan_id": saved["id"],
            "plan_version": saved["version"],
        },
    )
    assert failed_snapshot_response.status_code == 201
    failed_snapshot = failed_snapshot_response.json()
    failed_status = client.get(
        f"/api/projects/{project['id']}/snapshots/{failed_snapshot['id']}/projection"
    ).json()
    assert failed_status["status"] == "failed"
    assert "synthetic graph unavailable" in failed_status["last_error"]
    assert client.get(
        f"/api/projects/{project['id']}/snapshots/{failed_snapshot['id']}"
    ).status_code == 200

    monkeypatch.setattr(
        graph_projection,
        "project_graph",
        lambda projection: GraphProjectionResult(
            project_id=projection.project_id,
            snapshot_id=projection.snapshot_id,
            projected_nodes=len(projection.nodes),
            projected_edges=len(projection.edges),
        ),
    )
    retry = client.post(
        f"/api/projects/{project['id']}/snapshots/{failed_snapshot['id']}/projection/retry"
    )
    assert retry.status_code == 202
    assert _poll_task(client, retry.json()["id"])["status"] == "succeeded"
    assert client.get(
        f"/api/projects/{project['id']}/snapshots/{failed_snapshot['id']}/projection"
    ).json()["status"] == "succeeded"

    frozen_fact_ids = {item["id"] for item in snapshot["frozen_facts"]}
    changed_measurement = next(
        confirmed[item["id"]]
        for item in measurements
        if item["id"] in frozen_fact_ids
    )
    disputed = client.patch(
        f"/api/projects/{project['id']}/facts/{changed_measurement['id']}/status",
        json={
            "expected_version": changed_measurement["version"],
            "from_status": "user_confirmed",
            "to_status": "disputed",
            "actor": "integration-reviewer",
            "reason": "source interpretation changed",
        },
    )
    assert disputed.status_code == 200
    impacted = client.get(
        f"/api/projects/{project['id']}/snapshots/{snapshot['id']}"
    ).json()
    assert impacted["review_status"] == "needs_review"
    assert impacted["review_reasons"]

    history = client.get(f"/api/projects/{project['id']}/snapshots").json()
    assert len(history["items"]) == 2
    conflict = client.patch(
        f"/api/projects/{project['id']}",
        json={"expected_version": 1, "title": "stale overwrite"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current_version"] == 2
