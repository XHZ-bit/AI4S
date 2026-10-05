"""Evidence-backed reading, experiment records, research questions and quality operations."""

import json
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.sqlite import connect, get_paper
from app.db.workspace import document_view, get_state, put_state
from app.pipeline.evidence import knowledge_list

router = APIRouter(prefix="/api/learning", tags=["learning"])


def require_paper(conn, uid):
    paper = get_paper(conn, uid)
    if paper is None:
        raise HTTPException(404, "论文不存在")
    return paper


@router.get("/papers/{uid}")
def workspace(uid: str):
    with closing(connect()) as conn:
        paper = require_paper(conn, uid)
        docs = document_view(conn, uid)
        knowledge = knowledge_list(conn, uid)
        protocol_row = conn.execute(
            "SELECT data_json FROM protocols WHERE paper_uid=?", (uid,)
        ).fetchone()
        protocol = json.loads(protocol_row["data_json"]) if protocol_row else None
        if protocol and not protocol.get("verified"):
            protocol = None
        passages = docs[0]["passages"] if docs else []
        tasks = [
            {
                "id": f"read:{p['id']}",
                "heading": p["heading"],
                "passage_id": p["id"],
                "minutes": max(5, len(p["text"]) // 150),
                "criterion": "用自己的话说明本段的问题、方法或证据，并指出仍不理解的地方。",
            }
            for p in passages
        ]
        return {
            "paper": paper,
            "protocol": protocol,
            "documents": docs,
            "knowledge": knowledge,
            "reading_tasks": tasks,
            "stages": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM pipeline_stages WHERE paper_uid=?", (uid,)
                )
            ],
            "checks": [
                {
                    "id": "problem",
                    "question": "论文要解决什么问题？原文哪一段支持你的回答？",
                },
                {"id": "method", "question": "方法的输入、输出和关键机制是什么？"},
                {
                    "id": "evidence",
                    "question": "哪项实验支持主要结论？它在什么条件下成立？",
                },
                {
                    "id": "limits",
                    "question": "作者明确指出了哪些限制？哪些是你自己的推测？",
                },
            ],
            "reproduction": {
                "verified": bool(protocol),
                "code_url": paper.get("code_url"),
                "notice": (
                    "已登记维护者实测记录；只适用于下方指定范围、版本和环境。"
                    if protocol
                    else "尚无维护者实测记录。这里只提供准备清单，不代表已复现论文结果。"
                ),
                "steps": [
                    "确认官方仓库、许可证与提交版本",
                    "记录环境、算力、数据来源和下载规模",
                    "依据官方说明运行最小示例并保存日志",
                    "在相同设置下比较指标，记录差异和失败原因",
                ],
            },
            **get_state(conn, uid),
        }


class StateUpdate(BaseModel):
    version: int = Field(ge=0)
    state: dict


@router.patch("/papers/{uid}")
def save_workspace(uid: str, req: StateUpdate):
    allowed = {"reading", "answers", "experiments", "questions", "profile"}
    if set(req.state) - allowed or len(json.dumps(req.state)) > 500000:
        raise HTTPException(422, "工作区字段不合法或内容过大")
    expected = {
        "reading": dict,
        "answers": dict,
        "experiments": list,
        "questions": list,
        "profile": dict,
    }
    if any(not isinstance(v, expected[k]) for k, v in req.state.items()):
        raise HTTPException(422, "工作区数据类型不正确")
    with closing(connect()) as conn:
        require_paper(conn, uid)
        try:
            return put_state(conn, uid, req.state, req.version)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.get("/evidence/{pid}")
def evidence(pid: str):
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT p.*,d.paper_uid,d.coverage,d.created_at FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=?",
            (pid,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "证据不存在")
        return dict(row)


class Feedback(BaseModel):
    kind: Literal[
        "not_understood",
        "unclear",
        "broken_link",
        "experiment_failed",
        "suspected_error",
    ]
    detail: str = Field(min_length=1, max_length=4000)


@router.post("/papers/{uid}/feedback", status_code=201)
def feedback(uid: str, req: Feedback):
    with closing(connect()) as conn:
        require_paper(conn, uid)
        fid = conn.execute(
            "INSERT INTO feedback(paper_uid,kind,detail) VALUES(?,?,?)",
            (uid, req.kind, req.detail),
        ).lastrowid
        conn.commit()
        return {"id": fid, "status": "open"}


@router.get("/compare")
def compare(uids: str = Query(max_length=2000)):
    ids = list(dict.fromkeys(uids.split(",")))[:8]
    with closing(connect()) as conn:
        items = []
        for uid in ids:
            paper = require_paper(conn, uid)
            facts = [
                k for k in knowledge_list(conn, uid) if k["status"] == "human_verified"
            ]
            items.append(
                {
                    "uid": uid,
                    "title": paper["title"],
                    "year": paper["year"],
                    "claims": facts,
                    "comparison_status": "需逐项核对数据集、指标和实验条件，不能直接排名",
                }
            )
        return {"items": items}


@router.get("/quality")
def quality():
    with closing(connect()) as conn:
        return {
            "items": knowledge_list(conn),
            "feedback": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM feedback ORDER BY id DESC LIMIT 200"
                )
            ],
            "audit": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM audit_events ORDER BY id DESC LIMIT 200"
                )
            ],
        }


class QualityDecision(BaseModel):
    action: Literal["verify", "dispute", "withdraw", "restore"]
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/quality/{kid}")
def quality_decision(kid: int, req: QualityDecision):
    from app.api.review import _approve_entity, _approve_relation
    from app.db.proposals import get_proposal
    from app.graphsvc.entities import set_relation_quality

    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM knowledge WHERE id=?", (kid,)).fetchone()
        if not row:
            raise HTTPException(404, "知识不存在")
        before = dict(row)
        proposal = get_proposal(conn, kid)
        status = {
            "verify": "human_verified",
            "dispute": "disputed",
            "withdraw": "withdrawn",
            "restore": "candidate",
        }[req.action]
        if req.action == "verify":
            checks = json.loads(row["checks_json"])
            if not checks.get("evidence_located") or not checks.get("structure"):
                raise HTTPException(
                    422, "必须先具备可定位原文和合法结构，旧知识请重新抽取"
                )
            try:
                if proposal["kind"] == "entity":
                    _approve_entity(conn, proposal, proposal["payload"])
                else:
                    _approve_relation(conn, proposal, proposal["payload"])
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        if proposal["kind"] == "relation":
            try:
                set_relation_quality(conn, proposal, status)
            except Exception as exc:
                raise HTTPException(503, "图谱同步失败，状态未变更，请重试") from exc
        conn.execute(
            "UPDATE knowledge SET status=?,updated_at=datetime('now') WHERE id=?",
            (status, kid),
        )
        conn.execute(
            "UPDATE extraction_proposals SET status=? WHERE id=?",
            ("approved" if status == "human_verified" else "pending", kid),
        )
        conn.execute(
            "INSERT INTO audit_events(knowledge_id,action,actor,reason,before_json,after_json) VALUES(?,?,?,?,?,?)",
            (
                kid,
                req.action,
                req.actor,
                req.reason,
                json.dumps(before, ensure_ascii=False),
                json.dumps({"status": status}, ensure_ascii=False),
            ),
        )
        # Saved recommendations are marked stale, never silently rewritten.
        if status != "human_verified":
            guide = conn.execute(
                "SELECT result_json FROM guides WHERE paper_uid=?", (row["paper_uid"],)
            ).fetchone()
            if guide:
                content = json.loads(guide["result_json"])
                content["stale"] = True
                conn.execute(
                    "UPDATE guides SET result_json=? WHERE paper_uid=?",
                    (json.dumps(content, ensure_ascii=False), row["paper_uid"]),
                )
            for saved in conn.execute("SELECT id,result_json FROM roadmaps").fetchall():
                data = json.loads(saved["result_json"])
                if kid in data.get("knowledge_ids", []):
                    data["stale"] = True
                    conn.execute(
                        "UPDATE roadmaps SET result_json=? WHERE id=?",
                        (json.dumps(data, ensure_ascii=False), saved["id"]),
                    )
        conn.commit()
        return {"status": status}


@router.get("/tasks")
def tasks():
    with closing(connect()) as conn:
        return {
            "items": [
                dict(r)
                for r in conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 100")
            ]
        }


@router.get("/tasks/{tid}")
def task(tid: int):
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在")
        return {
            **dict(row),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }


@router.post("/tasks/{tid}/retry", status_code=202)
def retry(tid: int):
    from app.jobs import enqueue

    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if not row:
            raise HTTPException(404, "任务不存在")
        partial = row["status"] == "done" and bool(
            json.loads(row["result_json"] or "{}").get("warnings")
        )
        if row["status"] != "failed" and not partial:
            raise HTTPException(409, "只能重试失败或部分成功任务")
        kind = row["type"]
        params = json.loads(row["params_json"])
    try:
        return {"task_id": enqueue(kind, params)}
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.post("/papers/{uid}/guide", status_code=202)
def start_guide(uid: str):
    from app.jobs import enqueue

    with closing(connect()) as conn:
        require_paper(conn, uid)
    try:
        return {"task_id": enqueue("guide", {"uid": uid})}
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.get("/papers/{uid}/guide")
def get_guide(uid: str):
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM guides WHERE paper_uid=?", (uid,)).fetchone()
        if not row:
            return {"guide": None}
        data = json.loads(row["result_json"])
        docs = document_view(conn, uid)
        data["stale"] = data.get("stale", False) or bool(
            docs and docs[0]["id"] != row["document_id"]
        )
        return {"guide": data, "created_at": row["created_at"]}
