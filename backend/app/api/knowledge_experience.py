"""Project-scoped graph learning APIs. Every route validates a real project."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.workbench import project_or_404
from app.knowledge import experience, learning_checks, learning_experiences, learning_summary, store


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


class ExperienceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    practice_id: str = Field(min_length=1, max_length=200)


class CheckAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_id: str = Field(min_length=1, max_length=80)
    expected_context: str = Field(min_length=1, max_length=100)
    explanation: str = Field(default='', max_length=4000)


@router.get('/checks/recommendation')
def check_recommendation(project_id: str):
    with store.connection(project_id) as conn:
        return learning_checks.recommendation(conn, project_id)


@router.get('/nodes/{node_id}/checks')
def node_checks(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return learning_checks.get_checks(conn, project_id, node_id)


@router.post('/nodes/{node_id}/checks/{check_id}', status_code=201)
def answer_check(project_id: str, node_id: str, check_id: str, req: CheckAnswer):
    with store.connection(project_id) as conn:
        return learning_checks.submit(conn, project_id, node_id, check_id, req.answer_id, req.expected_context, req.explanation)


@router.post('/nodes/{node_id}/checks/{attempt_id}/dismiss')
def dismiss_check(project_id: str, node_id: str, attempt_id: str):
    with store.connection(project_id) as conn:
        return learning_checks.dismiss(conn, project_id, node_id, attempt_id)


@router.get("/paths")
def paths(project_id: str, source: str, target: str | None = None,
          kind: Literal["connection", "prerequisites"] = "connection", max_depth: int = Query(4, ge=1, le=6)):
    with store.connection(project_id) as conn:
        return experience.paths(conn, project_id, source, target, kind, max_depth)


@router.get("/progress")
def all_progress(project_id: str):
    with store.connection(project_id) as conn:
        return experience.all_progress(conn, project_id)


@router.get("/progress/summary")
def project_summary(project_id: str):
    with store.connection(project_id) as conn:
        return learning_summary.project_summary(conn, project_id)


@router.post("/progress/summary")
def explain_project_summary(project_id: str):
    return learning_summary.explain_project(project_id)


@router.get("/nodes/{node_id}/progress")
def progress(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return experience.progress(conn, project_id, node_id)


@router.get("/nodes/{node_id}/experiences")
def experiences(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return {"items": learning_experiences.list_entries(conn, project_id, node_id)}


@router.post("/nodes/{node_id}/experiences", status_code=201)
def save_experience(project_id: str, node_id: str, req: ExperienceCreate):
    with store.connection(project_id) as conn:
        return learning_experiences.save(conn, project_id, node_id, req.practice_id, req.content)


@router.get("/nodes/{node_id}/summary")
def node_summary(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return learning_summary.node_summary(conn, project_id, node_id)


@router.post("/nodes/{node_id}/summary")
def explain_node_summary(project_id: str, node_id: str):
    return learning_summary.explain(project_id, node_id)


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
