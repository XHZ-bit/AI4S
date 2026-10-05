"""审核 API：队列查询 + approve/edit/reject 决策（approve 即写图）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.proposals import (
    get_proposal,
    list_proposals,
    save_entity_vector,
    update_status,
)
from app.db.sqlite import connect
from app.graphsvc import entities
from app.pipeline.extract import canonical_uid

router = APIRouter(prefix="/api/review", tags=["review"])


def _connect():
    return connect()


class DecisionReq(BaseModel):
    action: str
    payload: dict | None = None


@router.get("/queue")
def queue(kind: str | None = None, paper_uid: str | None = None) -> dict:
    conn = _connect()
    try:
        items = list_proposals(conn, status="pending", kind=kind)
        if paper_uid:
            items = [i for i in items if i["paper_uid"] == paper_uid]
        return {"items": items}
    finally:
        conn.close()


def _require(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not value:
        raise ValueError(f"payload missing required field: {key}")
    return value


def _approve_entity(conn, p: dict, payload: dict) -> None:
    etype = _require(payload, "type")
    name = _require(payload, "name")
    entities.validate_entity_type(etype)
    uid = payload.get("canonical_uid") or entities.find_entity_uid_by_name(conn, name, etype) or canonical_uid(etype, name)
    entities.merge_entity(etype, uid, name)
    entities.merge_relation("MENTIONS", p["paper_uid"], uid)
    if not entities.find_entity_uid_by_name(conn, name, etype):
        vec = p.get("embedding")
        if vec:
            save_entity_vector(conn, uid, name, vec)
        else:
            conn.execute(
                "INSERT OR REPLACE INTO entity_vectors (uid, name, vector) VALUES (?, ?, X'0000000000000000')",
                (uid, name),
            )
        conn.commit()


def _approve_relation(conn, p: dict, payload: dict) -> None:
    rel = _require(payload, "rel_type")
    entities.validate_relation_type(rel)
    src_type = payload.get("src_type", "concept")
    dst_type = payload.get("dst_type", "concept")
    src_name = _require(payload, "src_name")
    dst_name = _require(payload, "dst_name")
    src_uid = payload.get("src_uid") or entities.find_entity_uid_by_name(conn, src_name, src_type) or canonical_uid(src_type, src_name)
    dst_uid = payload.get("dst_uid") or entities.find_entity_uid_by_name(conn, dst_name, dst_type) or canonical_uid(dst_type, dst_name)
    entities.merge_entity(src_type, src_uid, src_name)
    entities.merge_entity(dst_type, dst_uid, dst_name)
    entities.merge_relation(rel, src_uid, dst_uid)
    entities.merge_relation("MENTIONS", p["paper_uid"], src_uid)
    entities.merge_relation("MENTIONS", p["paper_uid"], dst_uid)


@router.post("/{pid}/decision")
def decide(pid: int, req: DecisionReq) -> dict:
    conn = _connect()
    try:
        p = get_proposal(conn, pid)
        if p is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        payload = req.payload if req.action == "edit" and req.payload else p["payload"]
    
        if p["status"] != "pending":
            conn.close()
            raise HTTPException(status_code=409, detail="Already decided; use the quality workbench to withdraw or restore")
    
        if req.action == "reject":
            update_status(conn, pid, "rejected")
            return {"status": "ok", "decision": "rejected"}
    
        if req.action not in ("approve", "edit"):
            raise HTTPException(status_code=400, detail="invalid action")
    
        try:
            if p["kind"] == "entity":
                _approve_entity(conn, p, payload)
            else:
                _approve_relation(conn, p, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    
        update_status(conn, pid, "approved", edited_payload=payload if req.action == "edit" else None)
        return {"status": "ok", "decision": "approved"}
    finally:
        conn.close()
