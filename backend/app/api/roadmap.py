from contextlib import closing
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError
from app.db.roadmaps import get_roadmap, list_roadmaps, update_item_done
from app.db.sqlite import connect
from app.models.roadmap import GenerateRequest
from app.roadmap.generate import generate_roadmap

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


def _connect():
    return connect()


class ProgressReq(BaseModel):
    phase: int | None = None
    item_index: int | None = None
    task_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    done: bool


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
