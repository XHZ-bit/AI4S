"""Project-scoped graph learning APIs. Every route validates a real project."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.workbench import project_or_404
from app.knowledge import experience, store


def project_scope(project_id: str):
    with store.connection() as conn:
        project_or_404(conn, project_id)


router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge-experience"], dependencies=[Depends(project_scope)])


class ProgressPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_started", "in_progress", "understood", "review"]
    expected_version: int | None = Field(default=None, ge=0)


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=250)
    url: str = Field(min_length=8, max_length=3000)
    type: Literal["paper", "tutorial", "image", "code", "video"] = "tutorial"
    reason: str = Field(default="用户补充的学习资源", max_length=1500)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


@router.get("/paths")
def paths(project_id: str, source: str, target: str | None = None,
          kind: Literal["connection", "prerequisites"] = "connection", max_depth: int = Query(4, ge=1, le=6)):
    with store.connection(project_id) as conn:
        return experience.paths(conn, project_id, source, target, kind, max_depth)


@router.get("/progress")
def all_progress(project_id: str):
    with store.connection(project_id) as conn:
        return experience.all_progress(conn, project_id)


@router.get("/nodes/{node_id}/progress")
def progress(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return experience.progress(conn, project_id, node_id)


@router.patch("/nodes/{node_id}/progress")
def save_progress(project_id: str, node_id: str, req: ProgressPatch):
    with store.connection(project_id) as conn:
        return experience.save_progress(conn, project_id, node_id, req.status, req.expected_version)


@router.get("/nodes/{node_id}/resources")
def resources(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return experience.resources(conn, project_id, node_id)


@router.post("/nodes/{node_id}/resources", status_code=201)
def add_resource(project_id: str, node_id: str, req: ResourceCreate):
    with store.connection(project_id) as conn:
        return experience.add_resource(conn, project_id, node_id, req.model_dump())


@router.post("/nodes/{node_id}/question")
def question(project_id: str, node_id: str, req: Question):
    return experience.ask(project_id, node_id, req.question)
