"""The learning loop keeps task progress, checks and mastery distinct."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.roadmaps import get_roadmap, update_item_done
from app.db.workflow import mastery_version, put_mastery, put_step_record
from app.models.roadmap import LearnerProfile
from app.roadmap.generate import generate_roadmap
from app.roadmap.replan import build_preview, save_replan
from app.workflow import activities, overview
from tests.test_roadmap_generate import setup_trusted


def test_route_completion_is_not_mastery_and_replan_keeps_history():
    conn = setup_trusted()
    original = generate_roadmap(LearnerProfile(goal="target", target_uid="method:target", weekly_hours=2), conn)
    target = original.phases[1].items[0]
    updated = update_item_done(conn, original.id, task_id=target.task_id, done=True, version=1)
    assert not conn.execute("SELECT 1 FROM workflow_mastery").fetchone()
    assert any(a["status"] == "completed" for a in activities(conn, "roadmap"))
    assert overview(conn)["counts"]["completed"] >= 1

    confirmed = put_mastery(conn, "concept:basics", 0, "confirm", "能解释基本概念", None)
    assert confirmed["confirmed"] == 1
    assert put_mastery(conn, "concept:basics", 1, "confirm", "能解释基本概念", None)["version"] == 1
    with pytest.raises(ValueError):
        put_mastery(conn, "concept:basics", 0, "revoke", "旧版本", None)

    preview = build_preview(conn, original.id, updated.version)
    assert [p["title"] for p in preview["roadmap"]["phases"]] == ["method:target"]
    assert preview["roadmap"]["phases"][0]["items"][0]["done"]
    assert preview["schedule"]["weekly_hours"] == 2
    with pytest.raises(ValueError):
        save_replan(conn, original.id, updated.version, "0" * 64)
    saved = save_replan(conn, original.id, updated.version, preview["input_fingerprint"])
    assert saved.parent_id == original.id
    assert saved.phases[0].items[0].done
    assert len(get_roadmap(conn, original.id).phases) == 2
    assert len(activities(conn, "roadmap")) == 1  # only current descendant in the active view

    revoked = put_mastery(conn, "concept:basics", 1, "revoke", "重新学习", None)
    assert revoked["confirmed"] == 0
    next_preview = build_preview(conn, saved.id, saved.version)
    assert [p["title"] for p in next_preview["roadmap"]["phases"]] == ["concept:basics", "method:target"]


def test_source_change_invalidates_preview_and_project_steps_are_versioned():
    conn = setup_trusted()
    route = generate_roadmap(LearnerProfile(goal="target", target_uid="method:target"), conn)
    preview = build_preview(conn, route.id, route.version)
    conn.execute("UPDATE knowledge SET status='withdrawn' WHERE layer='teaching'")
    conn.commit()
    with pytest.raises(ValueError):
        save_replan(conn, route.id, route.version, preview["input_fingerprint"])

    snapshot = {
        "id": "snapshot-1", "project_id": "project-1", "snapshot_version": 1,
        "plan": {"id": "plan-1", "title": "首轮验证", "steps": [
            {"id": "step-1", "title": "记录基线", "evidence_ids": []}
        ]},
    }
    conn.execute(
        "INSERT INTO research_snapshots(snapshot_id,project_id,snapshot_version,payload_json,review_status,created_at) "
        "VALUES(?,?,?,?,?,datetime('now'))",
        ("snapshot-1", "project-1", 1, json.dumps(snapshot), "current"),
    )
    conn.commit()
    before = activities(conn, "project")[0]
    assert before["status"] == "pending" and before["evidence_level"] == "none"
    saved = put_step_record(conn, "snapshot-1", "step-1", 0, True, "日志 A")
    assert saved["version"] == 1
    assert put_step_record(conn, "snapshot-1", "step-1", 1, True, "日志 A")["version"] == 1
    with pytest.raises(ValueError):
        put_step_record(conn, "snapshot-1", "step-1", 0, False, "冲突")
    assert activities(conn, "project")[0]["status"] == "completed"
    conn.execute("UPDATE research_snapshots SET review_status='needs_review' WHERE snapshot_id='snapshot-1'")
    conn.commit()
    assert activities(conn, "project")[0]["status"] == "needs_review"
    assert mastery_version(conn, "concept:basics")["confirmed"] == 0


def test_workflow_http_end_to_end(tmp_path, monkeypatch):
    from app.api import roadmap as roadmap_api
    from app.api import workflow as workflow_api
    from app.db.sqlite import connect

    source = setup_trusted()
    route = generate_roadmap(LearnerProfile(goal="target", target_uid="method:target"), source)
    db_path = str(tmp_path / "workflow.sqlite3")
    target = connect(db_path)
    source.backup(target)
    target.close()
    source.close()
    monkeypatch.setattr(workflow_api, "connect", lambda: connect(db_path))
    monkeypatch.setattr(roadmap_api, "_connect", lambda: connect(db_path))
    app = FastAPI()
    app.include_router(workflow_api.router)
    app.include_router(roadmap_api.router)
    client = TestClient(app)

    overview_response = client.get("/api/workflow/v1/overview")
    assert overview_response.status_code == 200
    assert overview_response.json()["counts"]["pending"] > 0
    target_response = client.get("/api/workflow/v1/activities", params={"source_kind": "roadmap"})
    assert target_response.status_code == 200
    assert target_response.json()["items"][0]["source_id"] == str(route.id)
    confirm = client.post(
        "/api/workflow/v1/mastery/concept:basics",
        json={"expected_version": 0, "action": "confirm", "reason": "可解释", "activity_id": None},
    )
    assert confirm.status_code == 200 and confirm.json()["confirmed"] == 1
    assert client.post(
        "/api/workflow/v1/mastery/concept:basics",
        json={"expected_version": 0, "action": "revoke", "reason": "旧版本"},
    ).status_code == 409
    preview = client.post(
        f"/api/roadmap/{route.id}/replan-preview", json={"expected_version": route.version}
    )
    assert preview.status_code == 200
    assert [p["title"] for p in preview.json()["roadmap"]["phases"]] == ["method:target"]
    commit = client.post(
        f"/api/roadmap/{route.id}/replan",
        json={"expected_version": route.version, "input_fingerprint": preview.json()["input_fingerprint"]},
    )
    assert commit.status_code == 200 and commit.json()["parent_id"] == route.id
    assert client.post(
        f"/api/roadmap/{route.id}/replan",
        json={"expected_version": route.version, "input_fingerprint": preview.json()["input_fingerprint"]},
    ).status_code == 409
