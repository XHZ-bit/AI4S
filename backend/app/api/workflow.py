"""Local single-user workflow aggregation and explicit execution evidence."""

from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.sqlite import connect
from app.db.workflow import mastery_version, put_mastery, put_step_record, step_record
from app.roadmap.trusted_queries import resolve_target
from app.workflow import activities, overview, recommendations

router = APIRouter(prefix="/api/workflow/v1", tags=["workflow"])


@router.get("/overview")
def get_overview():
    with closing(connect()) as conn:
        return overview(conn)


@router.get("/recommendations")
def get_recommendations():
    with closing(connect()) as conn:
        # Projection refresh writes disposable rows. Acquire the write lock before
        # reading to avoid upgrading an obsolete WAL snapshot during page refresh.
        conn.execute("BEGIN IMMEDIATE")
        result = recommendations(conn)
        conn.commit()
        return result


@router.get("/activities")
def get_activities(
    source_kind: Literal["roadmap", "paper", "case", "project"] | None = None,
    source_id: str | None = None,
    project_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    with closing(connect()) as conn:
        from app.db.projections import activity_page
        return activity_page(conn, source_kind, source_id, project_id, offset, limit)


@router.get('/agenda')
def agenda(minutes: int = Query(60, ge=5, le=480), source_id: str | None = None):
    from app.db.projections import refresh_activities
    import json
    with closing(connect()) as conn:
        refresh_activities(conn)
        rows = conn.execute("SELECT payload_json FROM activity_projection WHERE status_order IN (1,2) "
                            "AND (? IS NULL OR source_id=?) AND json_extract(payload_json,'$.estimated_minutes') IS NOT NULL "
                            "ORDER BY status_order,source_kind,title,id", (source_id, source_id))
        selected, used = [], 0
        for row in rows:
            item = json.loads(row[0])
            duration = item['estimated_minutes']
            if duration <= minutes - used:
                selected.append(item)
                used += duration
            if used == minutes:
                break
        unknown = conn.execute("SELECT COUNT(*) FROM activity_projection WHERE status_order IN (1,2) "
                               "AND (? IS NULL OR source_id=?) AND json_extract(payload_json,'$.estimated_minutes') IS NULL",
                               (source_id, source_id)).fetchone()[0]
        return {'items': selected, 'budget_minutes': minutes, 'estimated_minutes': used,
                'unscheduled_count': unknown,
                'notice': '优先继续进行中的活动，再安排待执行项；来源待复核项不进入排期。时长均为估算。'}


@router.get("/mastery")
def list_mastery():
    with closing(connect()) as conn:
        return {"items": [dict(row) for row in conn.execute(
            "SELECT concept_uid,confirmed,version,reason,activity_id,updated_at "
            "FROM workflow_mastery ORDER BY updated_at DESC,concept_uid"
        )]}


@router.get("/mastery/{concept_uid}")
def get_mastery(concept_uid: str):
    with closing(connect()) as conn:
        return mastery_version(conn, concept_uid)


class MasteryChange(BaseModel):
    expected_version: int = Field(ge=0)
    action: Literal["confirm", "revoke"]
    reason: str = Field(min_length=1, max_length=2000)
    activity_id: str | None = Field(default=None, max_length=500)


@router.post("/mastery/{concept_uid}")
def change_mastery(concept_uid: str, req: MasteryChange):
    with closing(connect()) as conn:
        if not req.reason.strip():
            raise HTTPException(422, "请填写确认或撤销理由")
        prior = mastery_version(conn, concept_uid)
        if req.action == "confirm" and resolve_target(conn, concept_uid, "human_verified") != concept_uid:
            raise HTTPException(422, "只能确认当前具备人工核验关系的概念或方法")
        if req.action == "revoke" and prior["version"] == 0:
            raise HTTPException(404, "尚无可撤销的掌握记录")
        if req.activity_id and not any(a["id"] == req.activity_id for a in activities(conn)):
            raise HTTPException(422, "关联任务不存在或已不在当前版本")
        try:
            return put_mastery(conn, concept_uid, req.expected_version, req.action,
                               req.reason.strip(), req.activity_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc


class StepRecordChange(BaseModel):
    expected_version: int = Field(ge=0)
    done: bool
    outcome: str = Field(default="", max_length=8000)


@router.get("/projects/{project_id}/snapshots/{snapshot_id}/steps/{step_id}")
def get_project_step(project_id: str, snapshot_id: str, step_id: str):
    with closing(connect()) as conn:
        _require_step(conn, project_id, snapshot_id, step_id)
        return step_record(conn, snapshot_id, step_id)


@router.post("/projects/{project_id}/snapshots/{snapshot_id}/steps/{step_id}")
def save_project_step(project_id: str, snapshot_id: str, step_id: str, req: StepRecordChange):
    with closing(connect()) as conn:
        snapshot = _require_step(conn, project_id, snapshot_id, step_id)
        if snapshot["review_status"] != "current":
            raise HTTPException(409, "快照依据已变化，请先复核；历史执行记录仍可查看")
        if req.done and not req.outcome.strip():
            raise HTTPException(422, "完成步骤时请记录产出或观察")
        try:
            return put_step_record(conn, snapshot_id, step_id, req.expected_version,
                                   req.done, req.outcome.strip())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc


def _require_step(conn, project_id, snapshot_id, step_id):
    from app.db.projects import get_snapshot

    snapshot = get_snapshot(conn, project_id, snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "快照不存在")
    value = snapshot.model_dump(mode="json")
    if not any(step["id"] == step_id for step in value["plan"]["steps"]):
        raise HTTPException(404, "快照步骤不存在")
    return value
