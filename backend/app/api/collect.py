from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.collector import service

router = APIRouter(prefix="/api/collect", tags=["collect"])


class CollectReq(BaseModel):
    keywords: list[str]
    categories: list[str]
    start_year: int = 2021
    max_results: int = Field(default=50, ge=1, le=200)

    @field_validator("start_year")
    @classmethod
    def _check_year(cls, v: int) -> int:
        if not 1900 <= v <= 2100:
            raise ValueError("start_year out of range")
        return v


@router.post("", status_code=202)
def trigger(req: CollectReq) -> dict:
    from app.jobs import enqueue
    try:
        task_id = enqueue("collect",req.model_dump())
    except RuntimeError as exc:
        raise HTTPException(429,str(exc)) from exc
    return {"task_id": task_id}


@router.get("/{task_id}")
def status(task_id: int) -> dict:
    row = service.get_task_status(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"id": row["id"], "status": row["status"], "error": row["error"]}
