"""Saved personal learning itineraries, separate from mastery self-assessment."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.api.knowledge_experience import project_scope
from app.knowledge import learning_routes, store

router = APIRouter(prefix='/api/projects/{project_id}/knowledge/learning-route',
                   tags=['knowledge-experience'], dependencies=[Depends(project_scope)])


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_node_id: str = Field(min_length=1, max_length=200)


class SaveInput(PreviewInput):
    expected_revision: int = Field(ge=0)
    preview_fingerprint: str = Field(min_length=1, max_length=100)


class RoutePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    step_node_id: str | None = Field(default=None, min_length=1, max_length=200)
    state: Literal['todo', 'done', 'skipped'] | None = None
    order: list[str] | None = Field(default=None, min_length=1, max_length=40)


class RecheckInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    step_node_id: str = Field(min_length=1, max_length=200)
    expected_context: str = Field(min_length=1, max_length=100)


@router.get('')
def read_route(project_id: str):
    with store.connection(project_id) as conn:
        return learning_routes.get(conn, project_id)


@router.post('/preview')
def preview_route(project_id: str, req: PreviewInput):
    with store.connection(project_id) as conn:
        return learning_routes.preview(conn, project_id, req.target_node_id)


@router.post('')
def save_route(project_id: str, req: SaveInput):
    with store.connection(project_id) as conn:
        return learning_routes.save(conn, project_id, req.target_node_id,
                                    req.expected_revision, req.preview_fingerprint)


@router.patch('')
def update_route(project_id: str, req: RoutePatch):
    with store.connection(project_id) as conn:
        return learning_routes.update(conn, project_id, req.model_dump())


@router.post('/recheck')
def recheck_route(project_id: str, req: RecheckInput):
    with store.connection(project_id) as conn:
        return learning_routes.recheck(conn, project_id, req.model_dump())


@router.get('/history')
def route_history(project_id: str):
    with store.connection(project_id) as conn:
        return learning_routes.history(conn, project_id)
