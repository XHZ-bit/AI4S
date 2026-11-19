"""Project-scoped personal graph nodes and their materials."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.api.knowledge_experience import project_scope
from app.knowledge import node_materials, sources, store

router = APIRouter(prefix='/api/projects/{project_id}/knowledge', tags=['knowledge-workspace'],
                   dependencies=[Depends(project_scope)])


class MaterialInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str = Field(min_length=1, max_length=200)
    note: str = Field(default='', max_length=4000)


class MaterialPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=4000)
    removed: bool | None = None


class NodeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=250)
    summary: str = Field(default='', max_length=30000)
    kind: Literal['concept', 'method', 'formula', 'experiment', 'finding'] = 'concept'


@router.post('/nodes', status_code=201)
def create_node(project_id: str, req: NodeInput):
    return node_materials.create_node(project_id, req.label, req.summary, req.kind)


@router.get('/nodes/{node_id}/materials')
def node_collection(project_id: str, node_id: str, include_removed: bool = False):
    with store.connection(project_id) as conn:
        return node_materials.collection(conn, project_id, node_id, include_removed=include_removed)


@router.post('/nodes/{node_id}/materials', status_code=201)
def attach(project_id: str, node_id: str, req: MaterialInput):
    with store.connection(project_id) as conn:
        return node_materials.bind(conn, project_id, node_id, req.source_id, req.note)


@router.post('/nodes/{node_id}/materials/upload', status_code=201)
def upload(project_id: str, node_id: str, file: Annotated[UploadFile, File()],
           kind: Annotated[Literal['paper', 'code', 'report', 'results'] | None, Form()] = None,
           note: Annotated[str, Form(max_length=4000)] = ''):
    # Validate ownership before accepting a large file or saving an original.
    with store.connection(project_id) as conn:
        store.record(conn, 'kw_nodes', project_id, node_id)
    raw = file.file.read(sources.MAX_BYTES + 1)
    if not raw or len(raw) > sources.MAX_BYTES:
        raise HTTPException(413, '资料为空或超过50 MB')
    return node_materials.upload(project_id, node_id, raw, file.filename or 'source.txt', kind, note)


@router.patch('/nodes/{node_id}/materials/{material_id}')
def revise(project_id: str, node_id: str, material_id: str, req: MaterialPatch):
    with store.connection(project_id) as conn:
        return node_materials.revise(conn, project_id, node_id, material_id, req.model_dump())


@router.get('/nodes/{node_id}/materials/{material_id}/history')
def history(project_id: str, node_id: str, material_id: str):
    with store.connection(project_id) as conn:
        return node_materials.history(conn, project_id, node_id, material_id)
