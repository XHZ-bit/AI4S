"""Audited candidate edits; published knowledge must be withdrawn before changing it."""

import json
from contextlib import closing
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db.sqlite import connect
from app.pipeline.evidence import ENDPOINTS, check_quote
from app.pipeline.schemas import ENTITY_TYPES

router = APIRouter(prefix="/api/learning/quality", tags=["curation"])


class Edit(BaseModel):
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    payload: dict


@router.patch("/{kid}")
def edit_candidate(kid: int, req: Edit):
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT k.*,p.kind,p.payload_json FROM knowledge k JOIN extraction_proposals p ON p.id=k.id WHERE k.id=?",
            (kid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Candidate not found")
        if row["status"] == "human_verified":
            raise HTTPException(409, "Withdraw the published record before editing")
        payload = req.payload
        passage = conn.execute(
            "SELECT * FROM passages WHERE id=?", (payload.get("passage_id"),)
        ).fetchone()
        if (
            passage
            and not conn.execute(
                "SELECT 1 FROM documents WHERE id=? AND paper_uid=?",
                (passage["document_id"], row["paper_uid"]),
            ).fetchone()
        ):
            raise HTTPException(422, "Evidence must belong to the same source document")
        if not passage:
            raise HTTPException(422, "Select a saved passage")
        quote = payload.get("evidence", "")
        if not isinstance(quote, str):
            raise HTTPException(422, "Evidence must be text")
        loc = check_quote(passage["text"], quote)
        if row["kind"] == "entity":
            valid = (
                payload.get("type") in ENTITY_TYPES
                and isinstance(payload.get("name"), str)
                and bool(payload["name"].strip())
            )
        else:
            allowed = ENDPOINTS.get(payload.get("rel_type"))
            valid = bool(
                allowed
                and payload.get("src_type") in allowed[0]
                and payload.get("dst_type") in allowed[1]
                and payload.get("src_name")
                and payload.get("dst_name")
            )
        if not valid or not loc["located"]:
            raise HTTPException(
                422, "Invalid endpoints or evidence is not an exact quotation"
            )
        before = dict(row)
        conn.execute(
            "UPDATE extraction_proposals SET payload_json=?,status='pending' WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), kid),
        )
        checks = {
            "structure": True,
            "evidence_located": True,
            "semantic": "needs_review",
            "conflict": "not_checked",
        }
        conn.execute(
            "UPDATE knowledge SET document_id=?,passage_id=?,quote=?,start_offset=?,end_offset=?,status='candidate',checks_json=?,updated_at=datetime('now') WHERE id=?",
            (
                passage["document_id"],
                passage["id"],
                quote,
                loc["start"],
                loc["end"],
                json.dumps(checks),
                kid,
            ),
        )
        conn.execute(
            "INSERT INTO audit_events(knowledge_id,action,actor,reason,before_json,after_json) VALUES(?,'edit',?,?,?,?)",
            (
                kid,
                req.actor,
                req.reason,
                json.dumps(before, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()
        return {"status": "candidate"}
