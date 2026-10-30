"""审核 API：队列查询 + approve/edit/reject 决策（approve 即写图）。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.proposals import (
    get_proposal,
    list_proposals,
)
from app.db.sqlite import connect
from app.graphsvc import entities

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
        from app.knowledge.unified import ledger

        canonical = {str(r["id"]): r for r in ledger(conn, project_id="library")}
        items = [
            {
                **item,
                "payload": canonical[str(item["id"])]["payload"],
                "quality_status": canonical[str(item["id"])]["status"],
            }
            if str(item["id"]) in canonical
            else item
            for item in items
            if canonical.get(str(item["id"]), {}).get("status")
            not in {"withdrawn", "rejected"}
        ]
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
    entities.validate_entity_type(_require(payload, "type"))
    _require(payload, "name")


def _approve_relation(conn, p: dict, payload: dict) -> None:
    entities.validate_relation_type(_require(payload, "rel_type"))
    for side in ("src", "dst"):
        entities.validate_entity_type(payload.get(side + "_type", "concept"))
        _require(payload, side + "_name")


@router.post("/{pid}/decision")
def decide(pid: int, req: DecisionReq) -> dict:
    conn = _connect()
    try:
        p = get_proposal(conn, pid)
        if p is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        payload = req.payload if req.action == "edit" and req.payload else p["payload"]

        from app.knowledge import store, unified

        store.init(conn)
        mapped = conn.execute(
            "SELECT record_id,record_table FROM kw_legacy_map WHERE scope_id='library' AND legacy_table='knowledge' AND legacy_id=?",
            (str(pid),),
        ).fetchone()
        if mapped and not unified.active(
            store.record(conn, mapped[1], "library", mapped[0])
        ):
            raise HTTPException(
                409, "该记录已撤回或来源已移除，请在质量工作台恢复后再操作"
            )

        if p["status"] != "pending":
            conn.close()
            raise HTTPException(
                status_code=409,
                detail="Already decided; use the quality workbench to withdraw or restore",
            )

        if req.action == "reject":
            conn.execute(
                "UPDATE extraction_proposals SET status='rejected' WHERE id=?", (pid,)
            )
            from app.knowledge.unified import sync_legacy

            sync_legacy(conn, kid=pid)
            conn.commit()
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

        import json

        conn.execute(
            "UPDATE extraction_proposals SET status='approved',payload_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), pid),
        )
        from app.knowledge.unified import sync_legacy

        sync_legacy(conn, kid=pid)
        conn.commit()
        return {"status": "ok", "decision": "approved"}
    finally:
        conn.close()
