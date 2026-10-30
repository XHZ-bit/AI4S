"""Node practice authoring and browser-reported teaching results; no host runner."""

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.knowledge import practice, store

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge-practice"])
Difficulty = Literal["foundation", "intermediate", "advanced"]


class Generate(BaseModel):
    goal: str = Field(default="", max_length=1000)
    difficulty: Difficulty = "foundation"
    adjustment: str = Field(default="", max_length=1500)
    refresh: bool = False
    previous_practice_id: str | None = Field(default=None, min_length=1, max_length=100)


class Draft(BaseModel):
    expected_revision: int = Field(ge=1)
    code: str = Field(max_length=50000)
    input_json: str = Field(max_length=12000)


class BrowserRun(BaseModel):
    status: Literal["success", "error", "timeout", "cancelled"]
    output: str = Field(default="", max_length=20000)
    code: str = Field(max_length=50000)
    input_json: str = Field(default="{}", max_length=12000)
    elapsed_ms: int = Field(ge=0, le=3600000)
    checked: bool = False
    passed: bool | None = None


@router.get("/nodes/{node_id}/practice")
def get_practice(project_id: str, node_id: str, goal: str | None = Query(default=None, max_length=1000),
                 difficulty: Difficulty | None = None, adjustment: str | None = Query(default=None, max_length=1500)):
    if goal is None and difficulty is None and adjustment is None:
        return practice.resume(project_id, node_id)
    return practice.get(project_id, node_id, goal or "", difficulty or "foundation", adjustment or "")


@router.post("/nodes/{node_id}/practice")
def generate_practice(project_id: str, node_id: str, body: Generate):
    return practice.generate(project_id, node_id, **body.model_dump())


@router.get("/practice/{practice_id}")
def get_version(project_id: str, practice_id: str):
    with store.connection(project_id) as conn:
        practice.init(conn)
        return practice.present(conn, project_id, practice.record(conn, project_id, practice_id))


@router.patch("/practice/{practice_id}")
def save_draft(project_id: str, practice_id: str, body: Draft):
    return practice.save_draft(project_id, practice_id, body.expected_revision, body.code, body.input_json)


@router.post("/practice/{practice_id}/runs", status_code=201)
def save_run(project_id: str, practice_id: str, body: BrowserRun):
    return practice.save_run(project_id, practice_id, body.model_dump())
