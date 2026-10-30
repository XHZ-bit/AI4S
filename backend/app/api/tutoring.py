import json
import hashlib
from time import perf_counter
from contextlib import closing
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import preferences
from app.db.sqlite import connect, get_paper
from app.learning_catalog import LESSONS, find_lesson, visible
from app.tutoring import store, make_plan, public_plan
from app.work_context import SourceSelection, resolve_selection

router = APIRouter(prefix="/api/tutor", tags=["tutoring"])


class TutorRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    scope: str | None = Field(default=None, max_length=100)
    phase: str = Field(default="full", pattern="^(full|explain|practice)$")
    question: str = Field(min_length=2, max_length=2000)
    paper_uid: str | None = Field(default=None, max_length=150)
    passage_id: str | None = Field(default=None, max_length=150)
    session_id: str | None = Field(default=None, max_length=50)
    source_context: SourceSelection | None = None


class QuizRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    question_index: int = Field(ge=0, le=20)
    answer: int = Field(ge=0, le=10)


class PracticeRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=100)
    exercise_id: str = Field(max_length=80)
    code: str = Field(max_length=20000)
    passed: bool
    output: str = Field(default="", max_length=4000)


def require_feature(name):
    if not preferences.enabled(name):
        raise HTTPException(409, "此功能已关闭，可在个人设置中重新开启")


def session_project(conn, identity, requested=None):
    from app.api.workbench import initialize

    initialize(conn)
    row = conn.execute(
        "SELECT project_id FROM project_tutor_sessions WHERE session_id=?", (identity,)
    ).fetchone()
    if row and requested and row[0] != requested:
        raise HTTPException(409, "辅导会话属于其他课题")
    return row[0] if row else requested


@router.get("/lessons")
def lessons():
    prefs = preferences.read()
    features = prefs["features"]
    with closing(connect()) as conn:
        store(conn)
        attempts = [
            dict(row)
            for row in conn.execute(
                "SELECT lesson_id,exercise_id,kind,result_json,created_at FROM learning_attempts ORDER BY id DESC LIMIT 200"
            )
        ]
    items = (
        [visible(item, features) for item in LESSONS]
        if any(features.get(key, True) for key in ("foundations", "quizzes", "coding"))
        else []
    )
    return {
        "items": items,
        "attempts": [
            {**a, "result": json.loads(a.pop("result_json"))} for a in attempts
        ],
    }


@router.post("/sessions", status_code=201)
def create_session(req: TutorRequest):
    request_started = perf_counter()
    require_feature("paper_guidance")
    prefs = preferences.read()
    source, history = None, []
    with closing(connect()) as conn:
        store(conn)
        if req.paper_uid:
            paper = get_paper(conn, req.paper_uid)
            if not paper:
                raise HTTPException(404, "论文不在当前空间")
            source = {
                "title": paper["title"],
                "abstract": (paper["abstract"] or "")[:3000],
            }
            if req.passage_id:
                row = conn.execute(
                    "SELECT p.text,p.heading,p.page FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=? AND d.paper_uid=?",
                    (req.passage_id, req.paper_uid),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "原文片段不属于当前论文")
                source["passage"] = {**dict(row), "text": row["text"][:8000]}
        if req.session_id:
            prior = conn.execute(
                "SELECT history_json,source_json,paper_uid FROM tutor_sessions WHERE id=?",
                (req.session_id,),
            ).fetchone()
            if not prior:
                raise HTTPException(404, "辅导记录不存在")
            req.project_id = session_project(conn, req.session_id, req.project_id)
            history = json.loads(prior[0])
            prior_source = json.loads(prior[1]) if prior[1] else None
            if prior_source and (
                not req.paper_uid
                or (
                    req.paper_uid == prior[2]
                    and not req.source_context
                    and (
                        not req.passage_id
                        or req.passage_id == prior_source.get("passage_id")
                    )
                )
            ):
                source = prior_source
                req.paper_uid = prior[2]
                req.passage_id = prior_source.get("passage_id")
        if req.source_context:
            selected = resolve_selection(conn, req.paper_uid, req.source_context)
            if req.passage_id and selected.get("passage_id") != req.passage_id:
                raise HTTPException(422, "选文与指定原文片段不一致，请重新选择")
            # An explicit new selection replaces the earlier source focus.
            # A copied selection that cannot be grounded stays user-authored.
            source = {
                key: value
                for key, value in (source or {}).items()
                if key
                not in {
                    "passage",
                    "passage_id",
                    "selection",
                    "selection_status",
                    "snapshot_sha256",
                }
            }
            source.update(selected)
            req.passage_id = selected.get("passage_id")
        if req.project_id:
            from app.api.workbench import initialize, project_or_404

            initialize(conn)
            project_or_404(conn, req.project_id)
            row = conn.execute(
                "SELECT features_json FROM project_learning_preferences WHERE project_id=?",
                (req.project_id,),
            ).fetchone()
            if row:
                flags = json.loads(row[0])
                prefs["features"] = {
                    k: v and flags.get(k, True) for k, v in prefs["features"].items()
                }
        if req.scope:
            scope = conn.execute(
                "SELECT features_json FROM learning_scopes WHERE name=?", (req.scope,)
            ).fetchone()
            if not scope:
                raise HTTPException(404, "学习课题不存在")
            overrides = json.loads(scope[0])
            prefs["features"] = {
                key: value and overrides.get(key, True)
                for key, value in prefs["features"].items()
            }
        if not prefs["features"].get("paper_guidance", True):
            raise HTTPException(409, "此课题辅导已关闭")
        if req.phase == "explain":
            prefs["features"] = {**prefs["features"], "coding": False, "quizzes": False}
        recent = conn.execute(
            "SELECT lesson_id,exercise_id,result_json FROM learning_attempts WHERE kind='quiz' ORDER BY id DESC LIMIT 20"
        ).fetchall()
        prefs["profile"] = {
            **prefs["profile"],
            "recent_checks": [dict(item) for item in recent],
            "knowledge_profile": learning_profile(conn),
        }
        if source:
            source = {**source, "paper_uid": req.paper_uid}
            source.setdefault(
                "snapshot_sha256",
                hashlib.sha256(
                    json.dumps(source, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest(),
            )
            if req.passage_id:
                source["passage_id"] = req.passage_id
    model_started = perf_counter()
    try:
        plan, model = make_plan(
            req.question, source, prefs["profile"], prefs["features"], history
        )
    except httpx.HTTPError:
        raise HTTPException(
            502, "模型连接失败，请检查个人设置中的模型配置或稍后重试"
        ) from None
    except (ValueError, KeyError, TypeError) as exc:
        message = (
            str(exc)
            if not isinstance(exc, (KeyError, TypeError)) and len(str(exc)) < 160
            else "模型回答格式不完整，请缩小问题后重试"
        )
        raise HTTPException(422, message) from None
    # This is the measured generation stage, including transport and response
    # validation, rather than an estimate of the provider's internal compute.
    model_seconds = round(perf_counter() - model_started, 4)
    identity = uuid4().hex
    history = [
        *history[-4:],
        {"question": req.question, "summary": plan["goal"], "steps": plan["steps"]},
    ]
    with closing(connect()) as conn:
        store(conn)
        stored_plan = {**plan, "_timings": {"model_seconds": model_seconds}}
        conn.execute(
            "INSERT INTO tutor_sessions(id,topic,paper_uid,plan_json,history_json,source_json) VALUES(?,?,?,?,?,?)",
            (
                identity,
                req.question,
                req.paper_uid,
                json.dumps(stored_plan, ensure_ascii=False),
                json.dumps(history, ensure_ascii=False),
                json.dumps(source, ensure_ascii=False),
            ),
        )
        if req.project_id:
            conn.execute(
                "INSERT INTO project_tutor_sessions VALUES(?,?)",
                (req.project_id, identity),
            )
        conn.commit()
    return {
        "id": identity,
        "model": model,
        "source": source,
        "plan": public_plan(plan),
        "timings": {
            "model_seconds": model_seconds,
            "total_seconds": round(perf_counter() - request_started, 4),
        },
    }


@router.get("/sessions")
def sessions():
    with closing(connect()) as conn:
        store(conn)
        return {
            "items": [
                dict(row)
                for row in conn.execute(
                    "SELECT id,topic,paper_uid,created_at FROM tutor_sessions ORDER BY created_at DESC,id DESC LIMIT 30"
                )
            ]
        }


@router.get("/sessions/{identity}")
def get_session(identity: str):
    require_feature("paper_guidance")
    with closing(connect()) as conn:
        store(conn)
        row = conn.execute(
            "SELECT * FROM tutor_sessions WHERE id=?", (identity,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "辅导记录不存在")
        plan = json.loads(row["plan_json"])
        timings = plan.pop("_timings", None)
        from app.api.stride_learning import features as scoped_features

        features = scoped_features(conn, session_project(conn, identity))
        if not features["paper_guidance"]:
            raise HTTPException(409, "此课题辅导已关闭")
        if not features["coding"]:
            plan["exercise"] = None
        if not features["quizzes"]:
            plan["quiz"] = []
            for step in plan["steps"]:
                step["check"] = ""
        if not features["glossary"]:
            plan["terms"] = []
        if not features["foundations"]:
            plan["prerequisites"] = []
        return {
            "id": identity,
            "plan": public_plan(plan),
            "model": "已保存的辅导",
            "source": json.loads(row["source_json"]) if row["source_json"] else None,
            **({"timings": timings} if timings else {}),
        }


def grade(identity, req, *, generated=False):
    require_feature("quizzes")
    with closing(connect()) as conn:
        store(conn)
        if generated:
            req.project_id = session_project(conn, identity, req.project_id)
        if req.project_id:
            from app.api.stride_learning import features
            from app.api.workbench import initialize

            initialize(conn)
            if not features(conn, req.project_id)["quizzes"]:
                raise HTTPException(409, "此课题小测已关闭")
        if generated:
            row = conn.execute(
                "SELECT plan_json FROM tutor_sessions WHERE id=?", (identity,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "辅导记录不存在")
            questions = json.loads(row[0])["quiz"]
        else:
            lesson = find_lesson(identity)
            if not lesson:
                raise HTTPException(404, "课程不存在")
            questions = lesson["quiz"]
        if req.question_index >= len(questions):
            raise HTTPException(422, "题目不存在")
        question = questions[req.question_index]
        if req.answer >= len(question["options"]):
            raise HTTPException(422, "选项不存在")
        result = {
            "correct": req.answer == question["answer"],
            "answer": question["answer"],
            "explanation": question["explanation"],
            "lesson_version": None
            if generated
            else lesson.get("version", "foundations-v1"),
        }
        conn.execute(
            "INSERT INTO learning_attempts(lesson_id,exercise_id,kind,answer_json,result_json,project_id) VALUES(?,?,'quiz',?,?,?)",
            (
                identity,
                str(req.question_index),
                json.dumps(req.model_dump()),
                json.dumps(result, ensure_ascii=False),
                req.project_id,
            ),
        )
        conn.commit()
        return result


@router.post("/lessons/{identity}/quiz")
def grade_lesson(identity: str, req: QuizRequest):
    return grade(identity, req)


@router.post("/sessions/{identity}/quiz")
def grade_session(identity: str, req: QuizRequest):
    return grade(identity, req, generated=True)


@router.post("/lessons/{identity}/practice")
def save_practice(identity: str, req: PracticeRequest):
    require_feature("coding")
    lesson = find_lesson(identity)
    if not lesson or lesson["exercise"]["id"] != req.exercise_id:
        raise HTTPException(404, "练习不存在")
    with closing(connect()) as conn:
        store(conn)
        if req.project_id:
            from app.api.stride_learning import features
            from app.api.workbench import initialize

            initialize(conn)
            if not features(conn, req.project_id)["coding"]:
                raise HTTPException(409, "此课题代码练习已关闭")
        result = {
            "passed": req.passed,
            "verification": "browser_self_reported",
            "output": req.output,
            "lesson_version": lesson.get("version", "foundations-v1"),
        }
        conn.execute(
            "INSERT INTO learning_attempts(lesson_id,exercise_id,kind,answer_json,result_json,project_id) VALUES(?,?,'code',?,?,?)",
            (
                identity,
                req.exercise_id,
                json.dumps({"code": req.code}),
                json.dumps(result, ensure_ascii=False),
                req.project_id,
            ),
        )
        conn.commit()
    return {"saved": True, **result}


@router.post("/sessions/{identity}/practice")
def save_session_practice(identity: str, req: PracticeRequest):
    require_feature("coding")
    with closing(connect()) as conn:
        store(conn)
        req.project_id = session_project(conn, identity, req.project_id)
        from app.api.stride_learning import features

        if not features(conn, req.project_id)["coding"]:
            raise HTTPException(409, "此课题代码练习已关闭")
        row = conn.execute(
            "SELECT plan_json FROM tutor_sessions WHERE id=?", (identity,)
        ).fetchone()
        exercise = json.loads(row[0]).get("exercise") if row else None
        if not exercise or exercise["id"] != req.exercise_id:
            raise HTTPException(404, "练习不存在")
        result = {
            "passed": req.passed,
            "verification": "browser_self_reported",
            "output": req.output,
        }
        conn.execute(
            "INSERT INTO learning_attempts(lesson_id,exercise_id,kind,answer_json,result_json,project_id) VALUES(?,?,'code',?,?,?)",
            (
                identity,
                req.exercise_id,
                json.dumps({"code": req.code}),
                json.dumps(result),
                req.project_id,
            ),
        )
        conn.commit()
    return {"saved": True, **result}


def learning_profile(conn):
    items = []
    for lesson in LESSONS:
        rows = conn.execute(
            "SELECT exercise_id,result_json,created_at FROM learning_attempts WHERE lesson_id=? AND kind='quiz' ORDER BY id DESC",
            (lesson["id"],),
        ).fetchall()
        latest = {}
        for row in rows:
            latest.setdefault(
                row["exercise_id"], json.loads(row["result_json"])["correct"]
            )
        correct = sum(latest.values())
        state = (
            "尚未检查"
            if not latest
            else "建议复习"
            if not all(latest.values())
            else "继续实践"
            if len(latest) >= len(lesson["quiz"])
            else "继续检查"
        )
        items.append(
            {
                "id": lesson["id"],
                "title": lesson["title"],
                "checked": len(latest),
                "correct": correct,
                "total": len(lesson["quiz"]),
                "state": state,
            }
        )
    return items


class ScopeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    features: preferences.Features


@router.post("/scopes")
def save_scope(req: ScopeRequest):
    with closing(connect()) as conn:
        store(conn)
        conn.execute(
            "INSERT INTO learning_scopes(name,features_json) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET features_json=excluded.features_json",
            (req.name.strip(), req.features.model_dump_json()),
        )
        conn.commit()
    return {"saved": True}


@router.get("/dashboard")
def dashboard():
    with closing(connect()) as conn:
        store(conn)
        return {
            "knowledge": learning_profile(conn),
            "scopes": [
                {"name": r[0], "features": json.loads(r[1])}
                for r in conn.execute(
                    "SELECT name,features_json FROM learning_scopes ORDER BY name"
                )
            ],
            "usage": [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM tutor_usage ORDER BY id DESC LIMIT 30"
                )
            ],
        }
