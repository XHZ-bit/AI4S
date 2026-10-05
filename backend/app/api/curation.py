"""Explicit maintainer inputs for source-backed teaching and tested protocols."""

import hashlib
import json
from contextlib import closing
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document, document_view
from app.db.proposals import save_proposal
from app.models.paper import ParsedPaper, Section
from app.pipeline.evidence import ENDPOINTS, check_quote

router = APIRouter(prefix="/api/learning", tags=["curation"])


class SourceCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    source_url: str = Field(min_length=8, max_length=2000)
    text: str = Field(min_length=1, max_length=100000)
    heading: str = Field(default="Teaching source", max_length=500)
    rel_type: str
    src_name: str = Field(min_length=1, max_length=500)
    src_type: str
    dst_name: str = Field(min_length=1, max_length=500)
    dst_type: str
    quote: str = Field(min_length=1, max_length=4000)
    actor: str = Field(min_length=1, max_length=100)
    conditions: str = Field(default="", max_length=4000)


@router.post("/sources", status_code=201)
def add_source(req: SourceCandidate):
    if not req.source_url.startswith("https://"):
        raise HTTPException(422, "Source must have an HTTPS URL")
    allowed = ENDPOINTS.get(req.rel_type)
    if not allowed or req.src_type not in allowed[0] or req.dst_type not in allowed[1]:
        raise HTTPException(422, "Invalid relationship endpoints")
    if req.quote not in req.text:
        raise HTTPException(422, "Quote must be an exact part of the source")
    uid = "source-" + hashlib.sha256(req.source_url.encode()).hexdigest()[:24]
    with closing(connect()) as conn:
        upsert_paper(
            conn,
            dict(
                uid=uid,
                arxiv_id=None,
                title=req.title,
                abstract="",
                authors=[],
                year=0,
                venue=None,
                categories=[],
                published=None,
                pdf_url=None,
                code_url=None,
                source="curated",
            ),
        )
        did = save_document(
            conn,
            uid,
            ParsedPaper(
                uid=uid,
                title=req.title,
                abstract="",
                sections=[Section(heading=req.heading, text=req.text)],
            ),
        )
        passage = next(
            (
                p
                for p in document_view(conn, uid)[0]["passages"]
                if req.quote in p["text"]
            ),
            None,
        )
        if not passage:
            raise HTTPException(
                422,
                "Quote crosses chunk bounds; select a shorter complete supporting passage",
            )
        payload = req.model_dump(exclude={"text", "title", "heading", "actor"})
        payload.update(document_id=did, passage_id=passage["id"], evidence=req.quote)
        if req.src_type == "paper" and req.src_name == req.title:
            payload["src_uid"] = uid
        kid = save_proposal(conn, uid, "relation", payload, 0)
        loc = check_quote(passage["text"], req.quote)
        checks = {
            "structure": True,
            "evidence_located": True,
            "semantic": "maintainer_candidate",
            "conflict": "not_checked",
        }
        conn.execute(
            "INSERT OR IGNORE INTO knowledge(id,paper_uid,document_id,passage_id,quote,start_offset,end_offset,layer,status,checks_json) VALUES(?,?,?,?,?,?,?,?,'candidate',?)",
            (
                kid,
                uid,
                did,
                passage["id"],
                req.quote,
                loc["start"],
                loc["end"],
                "teaching" if req.rel_type == "PREREQUISITE_OF" else "author_claim",
                json.dumps(checks),
            ),
        )
        conn.execute(
            "INSERT INTO audit_events(knowledge_id,action,actor,reason,before_json,after_json) VALUES(?,'create',?,'source candidate','{}',?)",
            (kid, req.actor, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return {"id": kid, "paper_uid": uid, "status": "candidate"}


class ProtocolStep(BaseModel):
    title: str
    inputs: str
    operation: str
    expected_output: str
    acceptance: str
    troubleshooting: str


class Protocol(BaseModel):
    scope: Literal["example", "small_scale", "paper"]
    repository: str
    commit: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    resources: str = Field(min_length=1)
    steps: list[ProtocolStep] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    maintainer: str = Field(min_length=1)
    tested_at: str = Field(min_length=1)
    test_log: str = Field(min_length=1)
    verified: bool = False


@router.put("/papers/{uid}/protocol")
def save_protocol(uid: str, req: Protocol):
    if not req.repository.startswith("https://"):
        raise HTTPException(422, "Repository must use HTTPS")
    with closing(connect()) as conn:
        if not conn.execute("SELECT 1 FROM papers WHERE uid=?", (uid,)).fetchone():
            raise HTTPException(404, "Paper not found")
        for pid in req.evidence_ids:
            if not conn.execute("SELECT 1 FROM passages WHERE id=?", (pid,)).fetchone():
                raise HTTPException(422, "Evidence missing")
        conn.execute(
            "INSERT INTO protocols(paper_uid,data_json) VALUES(?,?) ON CONFLICT(paper_uid) DO UPDATE SET data_json=excluded.data_json,updated_at=datetime('now')",
            (uid, req.model_dump_json()),
        )
        conn.commit()
        return req.model_dump()


@router.get("/papers/{uid}/protocol")
def get_protocol(uid: str):
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT * FROM protocols WHERE paper_uid=?", (uid,)
        ).fetchone()
        return {"protocol": json.loads(row["data_json"]) if row else None}


class FeedbackResolution(BaseModel):
    status: Literal["open", "investigating", "resolved"]


@router.patch("/feedback/{fid}")
def resolve_feedback(fid: int, req: FeedbackResolution):
    with closing(connect()) as conn:
        cur = conn.execute("UPDATE feedback SET status=? WHERE id=?", (req.status, fid))
        conn.commit()
        if not cur.rowcount:
            raise HTTPException(404, "Feedback not found")
        return {"status": req.status}
