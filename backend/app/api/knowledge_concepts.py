"""Local cross-paper concept discovery and explicit personal decisions."""

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.knowledge import concepts, store

router = APIRouter(prefix='/api/projects/{project_id}/knowledge/nodes/{node_id}/concept-correspondences',
                   tags=['knowledge-workspace'])
Decision = Literal['comparable', 'conditions_differ', 'uncertain', 'rejected']


class Versions(BaseModel):
    left_node_version: int | None = Field(default=None, ge=1)
    right_node_version: int | None = Field(default=None, ge=1)
    left_source_version: str | None = Field(default=None, max_length=200)
    right_source_version: str | None = Field(default=None, max_length=200)
    left_evidence_fingerprint: str | None = Field(default=None, max_length=100)
    right_evidence_fingerprint: str | None = Field(default=None, max_length=100)


class ConceptInput(Versions):
    other_node_id: str = Field(min_length=1, max_length=200)
    status: Decision = 'uncertain'
    explanation: str = Field(default='', max_length=3500)


class ConceptPatch(Versions):
    expected_revision: int = Field(ge=1)
    status: Decision
    explanation: str = Field(default='', max_length=3500)


@router.get('')
def get_collection(project_id: str, node_id: str, q: str = Query('', max_length=300), source_id: str | None = None):
    with store.connection(project_id) as conn:
        return concepts.collection(conn, project_id, node_id, q, source_id)


@router.post('')
def create(project_id: str, node_id: str, req: ConceptInput):
    with store.connection(project_id) as conn:
        return concepts.create(conn, project_id, node_id, req.model_dump())


@router.patch('/{correspondence_id}')
def revise(project_id: str, node_id: str, correspondence_id: str, req: ConceptPatch):
    with store.connection(project_id) as conn:
        return concepts.revise(conn, project_id, node_id, correspondence_id, req.model_dump())
