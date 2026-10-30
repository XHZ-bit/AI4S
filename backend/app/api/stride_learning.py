import json
from contextlib import closing
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.db.sqlite import connect
from app.api.stride import setup, state, write_state
from app.api.workbench import project_or_404
from app import preferences
from app.learning_catalog import LESSONS, visible
from app.diffusion_curriculum import LESSONS as DP, VERSION

router = APIRouter(prefix="/api/stride", tags=["learning-path"])


@router.post("/demo")
def create_demo():
    from pathlib import Path
    import shutil
    from app.db import projects
    from app.db.sqlite import upsert_paper
    from app.models.paper import PaperDoc
    from app.models.research import ResearchProjectCreate, PaperLinkCreate
    from app.api.papers import _data_dir
    from app import jobs

    sources = [
        (
            "2303.04137",
            "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion",
            2023,
            "method",
        ),
        ("2006.11239", "Denoising Diffusion Probabilistic Models", 2020, "background"),
        (
            "2304.13705",
            "Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware",
            2023,
            "baseline",
        ),
    ]
    with closing(connect()) as c:
        setup(c)
        previous = state(c, "__demo__", "diffusion-policy", {})
        if previous["data"].get("project_id"):
            existing = projects.get_project(c, previous["data"]["project_id"])
            if existing:
                return {"project_id": existing.id, "duplicate": True}
        p = projects.create_project(
            c,
            ResearchProjectCreate(
                title="Diffusion Policy：从理解到首轮实验",
                research_question="如何在明确观测、动作与评估条件下理解扩散策略，并设计可执行的验证实验？",
                domain="robot_policy_learning",
                constraints={
                    "version": 1,
                    "objective": "理解方法并准备最小验证实验",
                    "notes": ["教学示范课题；没有声明复现论文性能。"],
                },
            ),
        )
        bundle = Path(__file__).resolve().parents[3] / ".demo" / "paperstride"
        queued = []
        for uid, title, year, role in sources:
            if not c.execute("SELECT 1 FROM papers WHERE uid=?", (uid,)).fetchone():
                upsert_paper(
                    c,
                    PaperDoc(
                        uid=uid,
                        arxiv_id=uid,
                        title=title,
                        year=year,
                        pdf_url="https://arxiv.org/pdf/" + uid,
                    ).model_dump(),
                )
                c.commit()
            current = projects.get_project(c, p.id)
            projects.link_paper(
                c,
                p.id,
                current.version,
                PaperLinkCreate(
                    expected_project_version=current.version, paper_uid=uid, role=role
                ),
            )
            source = bundle / (uid + ".pdf")
            dest = _data_dir() / (uid + ".pdf")
            if source.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                queued.append(uid)
        write_state(
            c,
            "__demo__",
            "diffusion-policy",
            previous["version"],
            {"project_id": p.id},
            {},
        )
    if queued:
        try:
            jobs.enqueue("parse_batch", {"uids": queued})
        except RuntimeError:
            return {
                "project_id": p.id,
                "duplicate": False,
                "notice": "原文已保存，可立即阅读。队列忙时请在处理进度或论文页启动解析。",
            }
    return {"project_id": p.id, "duplicate": False, "parsing": queued}


def features(conn, pid):
    flags = preferences.read()["features"].copy()
    if pid:
        project_or_404(conn, pid)
        row = conn.execute(
            "SELECT features_json FROM project_learning_preferences WHERE project_id=?",
            (pid,),
        ).fetchone()
        if row:
            overrides = json.loads(row[0])
            flags = {k: v and overrides.get(k, True) for k, v in flags.items()}
    return flags


def default_edges():
    return [
        {"source": p, "target": x["id"], "origin": "teaching_suggestion"}
        for x in LESSONS
        for p in x["prerequisites"]
    ]


@router.get("/curriculum")
def curriculum(project_id: str | None = None, persona: str = "robotics"):
    with closing(connect()) as c:
        setup(c)
        flags = features(c, project_id)
        checks = []
        for lesson in DP:
            rows = c.execute(
                "SELECT * FROM learning_attempts WHERE lesson_id=? AND project_id IS ? ORDER BY id DESC",
                (lesson["id"], project_id),
            ).fetchall()
            latest = {}
            for r in rows:
                latest.setdefault((r["kind"], r["exercise_id"]), r)
            quizzes = [
                json.loads(r["result_json"])["correct"]
                for (kind, _), r in latest.items()
                if kind == "quiz"
            ]
            code = [
                json.loads(r["result_json"])["passed"]
                for (kind, _), r in latest.items()
                if kind == "code"
            ]
            status = "尚未检查"
            if rows:
                status = "需要复习"
                if (
                    len(quizzes) >= len(lesson["quiz"])
                    and all(quizzes)
                    and code
                    and all(code)
                ):
                    date = datetime.fromisoformat(
                        min(r["created_at"] for r in latest.values())
                    ).replace(tzinfo=timezone.utc)
                    status = (
                        "待复测"
                        if (datetime.now(timezone.utc) - date).days >= 7
                        else "本轮通过"
                    )
            checks.append(
                {
                    "id": lesson["id"],
                    "state": status,
                    "checked": len(quizzes),
                    "code_checked": bool(code),
                }
            )
        order = (
            ["dp-1", "dp-3", "dp-4", "dp-2", "dp-5"]
            if persona == "robotics"
            else ["dp-2", "dp-5", "dp-1", "dp-3", "dp-4"]
        )
        enabled = any(
            flags.get(k) for k in ("foundations", "quizzes", "coding", "visuals")
        )
        return {
            "version": VERSION,
            "features": flags,
            "items": [
                visible(next(x for x in DP if x["id"] == i), flags) for i in order
            ]
            if enabled
            else [],
            "checks": checks,
            "persona": persona,
            "recommendation": "先补条件分布与扩散，再连接动作窗口。"
            if persona == "robotics"
            else "先理解观测、动作和控制评估，再核对扩散目标。",
        }


@router.get("/dependencies")
def dependencies(project_id: str | None = None):
    if not preferences.enabled("graph"):
        raise HTTPException(409, "图谱已关闭")
    with closing(connect()) as c:
        setup(c)
        flags = features(c, project_id)
        if not flags.get("graph"):
            raise HTTPException(409, "此课题图谱已关闭")
        value = state(c, project_id or "__personal__", "dependencies", default_edges())
        return {
            **value,
            "nodes": [{"id": x["id"], "title": x["title"]} for x in LESSONS],
        }


class Edge(BaseModel):
    source: str = Field(max_length=80)
    target: str = Field(max_length=80)
    origin: str = "user_input"


class Edges(BaseModel):
    version: int = Field(ge=0)
    edges: list[Edge] = Field(max_length=200)


@router.post("/dependencies")
def save_dependencies(req: Edges, project_id: str | None = None):
    if not preferences.enabled("graph"):
        raise HTTPException(409, "图谱已关闭")
    ids = {x["id"] for x in LESSONS}
    adj = {i: [] for i in ids}
    pairs = set()
    for e in req.edges:
        if e.source not in ids or e.target not in ids:
            raise HTTPException(422, "知识点不存在")
        if (e.source, e.target) in pairs:
            raise HTTPException(422, "重复依赖")
        pairs.add((e.source, e.target))
        adj[e.source].append(e.target)
    visiting = set()
    done = set()

    def visit(node):
        if node in visiting:
            raise HTTPException(422, "先修依赖不能形成循环")
        if node in done:
            return
        visiting.add(node)
        for other in adj[node]:
            visit(other)
        visiting.remove(node)
        done.add(node)

    for node in adj:
        visit(node)
    with closing(connect()) as c:
        setup(c)
        flags = features(c, project_id)
        if not flags.get("graph"):
            raise HTTPException(409, "此课题图谱已关闭")
        existing = state(
            c, project_id or "__personal__", "dependencies", default_edges()
        )["data"]
        origins = {
            (e["source"], e["target"]): e.get("origin", "user_input") for e in existing
        }
        return write_state(
            c,
            project_id or "__personal__",
            "dependencies",
            req.version,
            [
                {
                    "source": e.source,
                    "target": e.target,
                    "origin": origins.get((e.source, e.target), "user_input"),
                }
                for e in req.edges
            ],
            default_edges(),
        )


@router.get("/dependencies/history")
def dependency_history(project_id: str | None = None):
    with closing(connect()) as c:
        setup(c)
        features(c, project_id)
        return {
            "items": [
                {**dict(r), "data": json.loads(r["data"])}
                for r in c.execute(
                    "SELECT version,data,created_at FROM stride_history WHERE project_id=? AND kind='dependencies' ORDER BY id DESC LIMIT 30",
                    (project_id or "__personal__",),
                )
            ]
        }
