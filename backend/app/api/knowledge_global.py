"""Account-scoped knowledge overview; does not call models or migrate on reads."""

from fastapi import APIRouter, Query, HTTPException
from app.knowledge import store, unified
from pydantic import BaseModel, Field
from typing import Literal

router = APIRouter(prefix="/api/knowledge", tags=["unified-knowledge"])


@router.get("/graph")
def graph(
    project_id: str | None = None,
    q: str = Query("", max_length=300),
    kind: str | None = None,
    paper_uid: str | None = None,
    node_id: str | None = None,
    overview: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    with store.connection() as conn:
        return unified.graph(
            conn,
            project_id=project_id,
            q=q,
            kind=kind,
            paper_uid=paper_uid,
            node_id=node_id,
            overview=overview,
            limit=limit,
            offset=offset,
        )


@router.get("/nodes/{node_id}")
def node(node_id: str, project_id: str | None = None):
    with store.connection() as conn:
        return unified.detail(conn, node_id, project_id)


@router.get("/edges/{edge_id}")
def edge(edge_id: str, project_id: str | None = None):
    with store.connection() as conn:
        edge_id = unified.resolve_legacy_id(conn, edge_id, "kw_edges", project_id)
        row = conn.execute(
            "SELECT project_id FROM kw_edges WHERE id=?", (edge_id,)
        ).fetchone()
        if not row or (project_id is not None and project_id != row[0]):
            from fastapi import HTTPException

            raise HTTPException(404, "关系不存在")
        scope = unified.require_scope(conn, row[0])
        value = store.record(conn, "kw_edges", row[0], edge_id)
        return {
            "edge": value,
            "evidence": store.evidence(conn, row[0], value["evidence_ids"]),
            "scope": scope,
        }


class Quality(BaseModel):
    action: Literal["verify", "dispute", "withdraw", "restore"]
    actor: str | None = Field(default=None, min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)
    expected_version: int = Field(ge=1)
    project_id: str | None = None


@router.post("/records/{record_id}/quality")
def review(record_id: str, req: Quality):
    from app.tenancy import current_user
    user = current_user.get()
    actor = (user.get('username') or user.get('id')) if user else (req.actor or '本机用户')
    with store.connection() as conn:
        return unified.review_record(
            conn,
            record_id,
            req.action,
            actor,
            req.reason,
            project_id=req.project_id,
            expected_version=req.expected_version,
        )


@router.get('/records/{record_id}/history')
def history(record_id: str, project_id: str):
    import json
    with store.connection() as conn:
        unified.require_scope(conn, project_id)
        table = 'kw_nodes' if conn.execute('SELECT 1 FROM kw_nodes WHERE id=? AND project_id=?', (record_id, project_id)).fetchone() else 'kw_edges'
        current = store.record(conn, table, project_id, record_id)
        if current['project_id'] != project_id:
            raise HTTPException(404, '知识内容不在当前研究空间')
        rows = conn.execute('SELECT kind,data,created_at FROM kw_history WHERE project_id=? AND record_id=? ORDER BY id DESC LIMIT 30', (project_id, record_id)).fetchall()
        return {'items': [{'kind': row[0], 'snapshot': json.loads(row[1]), 'created_at': row[2]} for row in rows]}
