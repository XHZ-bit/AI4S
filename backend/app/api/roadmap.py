from contextlib import closing
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from app.db.roadmaps import get_roadmap, list_roadmaps, update_item_done
from app.db.sqlite import connect
from app.models.roadmap import GenerateRequest
from app.roadmap.generate import generate_roadmap
from app.roadmap.trusted_queries import list_targets
from app.roadmap.replan import build_preview, save_replan
from app.roadmap.auto_evaluate import evaluate_candidates
from app.roadmap.replan import _schedule

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


def _connect():
    return connect()


class ProgressReq(BaseModel):
    phase: int | None = None
    item_index: int | None = None
    task_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    done: bool


class ReplanPreviewReq(BaseModel):
    expected_version: int = Field(ge=1)


class ReplanCommitReq(ReplanPreviewReq):
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/targets")
def targets(q: str = "", preview: bool = False):
    with closing(_connect()) as conn:
        return {"items": list_targets(conn, q, "demo_curated" if preview else "human_verified")}


@router.get("/auto-targets")
def auto_targets(q: str = ""):
    with closing(_connect()) as conn:
        return {"items": list_targets(conn, q, "auto_checked")}


@router.post("/auto-preview")
def auto_preview(req: GenerateRequest):
    """Ephemeral machine-checked proposal; never creates a formal route."""
    with closing(_connect()) as conn:
        profile = req.profile
        if not profile.target_uid:
            raise HTTPException(422, "请先选择自动核查候选中的明确目标")
        check = evaluate_candidates(
            conn, profile.target_uid, {"current": profile.known_concepts}, status="auto_checked"
        )
        if not check["passed"]:
            raise HTTPException(422, {"message": "候选未通过自动核查", "failures": check["failures"]})
        try:
            route = generate_roadmap(profile, conn, status="auto_checked", persist=False)
            schedule = _schedule(route, conn, profile.weekly_hours)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"evidence_level": "machine_checked_preview", "route": route.model_dump(),
                "schedule": schedule, "checked_relations": check["checked_relations"],
                "notice": "仅通过来源、结构、环路和配置检查；教学关系与学习效果未获确认，不会保存为正式路线。"}


@router.post("/preview")
def preview(req: GenerateRequest):
    """Unpublished curation preview; uses the same planner without saving a formal route."""
    with closing(_connect()) as conn:
        try:
            return generate_roadmap(req.profile, conn, status="demo_curated", persist=False).model_dump()
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc


@router.post("/generate")
def generate(req: GenerateRequest):
    with closing(_connect()) as conn:
        try:
            return generate_roadmap(req.profile, conn).model_dump()
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, str(exc)) from exc


@router.post("/generate-async", status_code=202)
def generate_async(req: GenerateRequest):
    from app.jobs import enqueue

    try:
        return {"task_id": enqueue("roadmap", {"profile": req.profile.model_dump()})}
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.get("/{rid}")
def get(rid: int):
    with closing(_connect()) as conn:
        try:
            return get_roadmap(conn, rid).model_dump()
        except LookupError as exc:
            raise HTTPException(404, "roadmap not found") from exc


@router.post("/{rid}/replan-preview")
def replan_preview(rid: int, req: ReplanPreviewReq):
    with closing(_connect()) as conn:
        try:
            return build_preview(conn, rid, req.expected_version)
        except LookupError as exc:
            raise HTTPException(404, "roadmap not found") from exc
        except ValueError as exc:
            code = 409 if "已更新" in str(exc) else 422
            raise HTTPException(code, str(exc)) from exc


@router.post("/{rid}/replan")
def replan(rid: int, req: ReplanCommitReq):
    with closing(_connect()) as conn:
        try:
            return save_replan(conn, rid, req.expected_version, req.input_fingerprint).model_dump()
        except LookupError as exc:
            raise HTTPException(404, "roadmap not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("")
def list_all():
    with closing(_connect()) as conn:
        return {"items": list_roadmaps(conn)}


@router.patch("/{rid}/progress")
def progress(rid: int, req: ProgressReq):
    with closing(_connect()) as conn:
        try:
            return update_item_done(
                conn, rid, req.phase, req.item_index, req.done, req.task_id, req.version
            ).model_dump()
        except (LookupError, IndexError) as exc:
            raise HTTPException(404, "item not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
