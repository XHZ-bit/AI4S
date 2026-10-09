"""Offline case study, optimistic session state, bounded run imports and reports."""

import hashlib
import io
import json
import zipfile
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, ValidationError
from app.cases.catalog import CASE_ID, VERSION, SOURCES, STEP_IDS, QUESTIONS, catalog
from app.cases.validation import StrictModel, Bundle, validate_bundle
from app.db.sqlite import connect

router = APIRouter(prefix="/api/cases", tags=["cases"])
MAX_BUNDLE_BYTES = 1024 * 1024


def require_case(case_id):
    if case_id != CASE_ID:
        raise HTTPException(404, "专题不存在")


def read_session(conn, case_id, sid):
    require_case(case_id)
    row = conn.execute(
        "SELECT * FROM case_sessions WHERE id=? AND case_id=?", (sid, case_id)
    ).fetchone()
    if not row:
        raise HTTPException(404, "学习记录不存在")
    result = dict(row)
    result["state"] = json.loads(result.pop("state_json"))
    result["state"].setdefault("practice", {})
    result["state"].setdefault("practice_history", [])
    result["stale"] = result["case_version"] != VERSION
    result["runs"] = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "report": json.loads(r["report_json"]),
        }
        for r in conn.execute(
            "SELECT id,created_at,report_json FROM case_runs WHERE session_id=? ORDER BY id DESC",
            (sid,),
        )
    ]
    return result


def write_state(conn, case_id, sid, version, modify):
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = read_session(conn, case_id, sid)
        if current["stale"]:
            raise HTTPException(409, "专题版本已变化，请新建记录；旧记录仍保留")
        if current["version"] != version:
            raise HTTPException(409, "学习记录已在其他页面更新，请重新加载后保存")
        state = current["state"]
        modify(state)
        conn.execute(
            "UPDATE case_sessions SET state_json=?,version=version+1,updated_at=datetime('now') WHERE id=?",
            (json.dumps(state, ensure_ascii=False), sid),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return read_session(conn, case_id, sid)


@router.get("")
def list_cases():
    case = catalog()
    return {
        "items": [
            {
                k: case[k]
                for k in ("id", "title", "version", "status", "scope", "notice")
            }
        ]
    }


@router.get("/{case_id}")
def get_case(case_id: str):
    require_case(case_id)
    return catalog()


@router.get("/{case_id}/checker")
def download_checker(case_id: str):
    require_case(case_id)
    script = Path(__file__).resolve().parents[2] / "scripts" / "atlas_case_check.py"
    return Response(
        script.read_bytes(),
        media_type="text/x-python",
        headers={"Content-Disposition": 'attachment; filename="atlas_case_check.py"'},
    )


@router.get("/{case_id}/sources.zip")
def download_sources(case_id: str):
    require_case(case_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for source in SOURCES["files"]:
            archive.writestr(source["path"], source["text"])
        archive.writestr(
            "LICENSE",
            Path(__file__)
            .resolve()
            .parents[1]
            .joinpath("cases", "UPSTREAM_LICENSE.txt")
            .read_text(encoding="utf-8"),
        )
        archive.writestr(
            "ATLAS_SOURCE.json",
            json.dumps(
                {"commit": SOURCES["commit"], "repository": SOURCES["repository"]}
            ),
        )
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="atlas-sources.zip"'},
    )


@router.post("/{case_id}/sessions", status_code=201)
def new_session(case_id: str):
    require_case(case_id)
    sid = str(uuid4())
    state = {
        "current_step": "orient",
        "read_steps": [],
        "answers": {},
        "profile": {
            "goal": "理解方法并完成源码检查",
            "system": "Windows",
            "compute": "尚未确认",
        },
    }
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO case_sessions(id,case_id,case_version,state_json) VALUES(?,?,?,?)",
            (sid, case_id, VERSION, json.dumps(state, ensure_ascii=False)),
        )
        conn.commit()
        return read_session(conn, case_id, sid)


@router.get("/{case_id}/sessions")
def sessions(case_id: str):
    require_case(case_id)
    with closing(connect()) as conn:
        return {
            "items": [
                dict(r)
                for r in conn.execute(
                    "SELECT id,case_version,updated_at FROM case_sessions WHERE case_id=? ORDER BY updated_at DESC,rowid DESC LIMIT 20",
                    (case_id,),
                )
            ]
        }


@router.get("/{case_id}/sessions/{sid}")
def get_session(case_id: str, sid: str):
    with closing(connect()) as conn:
        return read_session(conn, case_id, sid)


class Profile(StrictModel):
    goal: str = Field(min_length=1, max_length=300)
    system: str = Field(min_length=1, max_length=100)
    compute: str = Field(min_length=1, max_length=100)


class SessionPatch(StrictModel):
    version: int = Field(ge=0)
    current_step: str | None = None
    read_step: str | None = None
    profile: Profile | None = None


@router.patch("/{case_id}/sessions/{sid}")
def update_session(case_id: str, sid: str, req: SessionPatch):
    for step in (req.current_step, req.read_step):
        if step is not None and step not in STEP_IDS:
            raise HTTPException(422, "未知步骤")

    def modify(state):
        if req.current_step is not None:
            state["current_step"] = req.current_step
        if req.read_step is not None and req.read_step not in state["read_steps"]:
            state["read_steps"].append(req.read_step)
        if req.profile is not None:
            state["profile"] = req.profile.model_dump()

    with closing(connect()) as conn:
        return write_state(conn, case_id, sid, req.version, modify)


class Answer(StrictModel):
    version: int = Field(ge=0)
    question_id: str = Field(max_length=80)
    choice: int = Field(ge=0, le=2)


@router.post("/{case_id}/sessions/{sid}/answers")
def answer(case_id: str, sid: str, req: Answer):
    question = next((q for q in QUESTIONS if q["id"] == req.question_id), None)
    if question is None:
        raise HTTPException(422, "理解问题不存在")

    def modify(state):
        previous = state["answers"].get(req.question_id, {})
        state["answers"][req.question_id] = {
            "choice": req.choice,
            "correct": req.choice == question["correct"],
            "explanation": question["explanation"],
            "attempts": previous.get("attempts", 0) + 1,
            "review_step": question["step"],
        }

    with closing(connect()) as conn:
        return write_state(conn, case_id, sid, req.version, modify)


@router.post("/{case_id}/sessions/{sid}/runs")
async def import_run(case_id: str, sid: str, request: Request):
    require_case(case_id)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BUNDLE_BYTES:
            raise HTTPException(413, "结果包超过 1 MiB，请导入工具生成的 JSON 摘要")
    try:
        bundle = Bundle.model_validate_json(raw)
        report = validate_bundle(bundle)
    except (ValidationError, ValueError) as exc:
        message = (
            "结果包格式不正确，请使用本页工具生成的原始 JSON"
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        raise HTTPException(422, message) from exc
    serialized = json.dumps(
        bundle.model_dump(), ensure_ascii=False, sort_keys=True, allow_nan=False
    )
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    with closing(connect()) as conn:
        current = read_session(conn, case_id, sid)
        if current["stale"]:
            raise HTTPException(409, "专题版本已变化，请新建学习记录")
        # Insertion is idempotent; state/answers are never overwritten by run import.
        conn.execute(
            "INSERT OR IGNORE INTO case_runs(session_id,digest,bundle_json,report_json) VALUES(?,?,?,?)",
            (sid, digest, serialized, json.dumps(report, ensure_ascii=False)),
        )
        conn.commit()
        return read_session(conn, case_id, sid)


@router.get("/{case_id}/sessions/{sid}/report")
def report(case_id: str, sid: str):
    with closing(connect()) as conn:
        session = read_session(conn, case_id, sid)
        latest = conn.execute(
            "SELECT bundle_json FROM case_runs WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (sid,),
        ).fetchone()
    lines = [
        "# Research Atlas 学习与源码检查报告",
        "",
        f"学习记录：{sid}",
        f"专题版本：{session['case_version']}",
        f"固定提交：{SOURCES['commit']}",
        "",
        catalog()["notice"],
        "",
        "## 理解记录",
    ]
    for q in QUESTIONS:
        a = session["state"]["answers"].get(q["id"])
        status = (
            "未作答"
            if not a
            else ("本题正确，不代表全面掌握" if a["correct"] else "需要回顾")
        )
        lines.append(f"- {q['question']}：{status}")
    lines.extend(["", "## 交互练习"])
    for identity, result in session["state"]["practice"].items():
        lines.append(f"- {identity}：{'答对' if result['correct'] else '需回顾'}，{result['attempts']} 次不同作答；{result['explanation']}")
    if not session["state"]["practice"]:
        lines.append("尚未提交交互练习。")
    lines.extend(["", "## 最新导入结果"])
    if latest:
        bundle = json.loads(latest["bundle_json"])
        summary = session["runs"][0]["report"]
        lines.extend(
            [
                "记录一致性：" + ("通过" if summary["passed"] else "需处理"),
                summary["verification"],
                f"记录时间：{bundle['created_at']}",
                "环境：" + json.dumps(bundle["environment"], ensure_ascii=False),
            ]
        )
        lines.extend(
            f"- {r['label']}：{'通过' if r['passed'] else '未通过'}"
            for r in summary["checks"]
        )
    else:
        lines.append("尚未导入检查记录。")
    lines.extend(["", "## 来源", f"- 论文入口：{catalog()['paper_url']}"])
    lines.extend(f"- {f['path']}：{f['url']}" for f in SOURCES["files"])
    lines.extend(
        [
            "",
            "## 未完成与下一步",
            "- 尚未进行策略评估或训练，不报告论文复现成功率。",
            "- 论文主张仍需领域核验。",
            "- 在独立环境中固定检查点和实验设置，保存真实评估日志。",
        ]
    )
    return Response(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="atlas-case-report.md"'},
    )
