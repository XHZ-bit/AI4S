"""Read-only projection of existing work into one local execution view."""

from urllib.parse import quote

from app.cases.catalog import CASE_ID, QUESTIONS, VERSION
from app.db.roadmaps import get_roadmap
from app.db.workflow import latest_snapshots, step_record
from app.db.workspace import get_state


CHECKS = (
    ("problem", "论文要解决什么问题？"),
    ("method", "方法的输入、输出和关键机制是什么？"),
    ("evidence", "哪项实验支持主要结论？"),
    ("limits", "作者明确指出了哪些限制？"),
)


def _activity(kind, source_id, version, item_id, title, status, evidence_level, url,
              *, detail="", estimated_minutes=None, evidence_ids=None, project_id=None):
    return {
        "id": f"{kind}:{source_id}:{item_id}", "source_kind": kind,
        "source_id": str(source_id), "source_version": version,
        "item_id": str(item_id), "title": title, "status": status,
        "evidence_level": evidence_level, "url": url, "detail": detail,
        "estimated_minutes": estimated_minutes, "evidence_ids": evidence_ids or [],
        "project_id": project_id,
    }


def _roadmap_activities(conn):
    rows = conn.execute(
        "SELECT id FROM roadmaps WHERE id NOT IN (SELECT parent_id FROM workflow_roadmap_lineage) ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        route = get_roadmap(conn, row["id"])
        for phase in route.phases:
            for index, item in enumerate(phase.items):
                key = item.task_id or f"legacy:{phase.phase}:{index}"
                status = "needs_review" if route.stale else "completed" if item.done else "pending"
                yield _activity(
                    "roadmap", str(row["id"]), route.version, key, item.title,
                    status, "recorded" if item.done else "none",
                    f"/roadmap?id={row['id']}", detail=item.reason,
                    estimated_minutes=item.estimated_minutes,
                    evidence_ids=item.evidence_ids,
                )


def _paper_activities(conn):
    rows = conn.execute("SELECT uid,title FROM papers ORDER BY created_at DESC,uid DESC").fetchall()
    for paper in rows:
        uid = paper["uid"]
        state = get_state(conn, uid)
        doc = conn.execute(
            "SELECT id,content_hash FROM documents WHERE paper_uid=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
            (uid,),
        ).fetchone()
        if not doc:
            continue
        url = f"/papers/{quote(uid, safe='')}?tab=reading"
        for p in conn.execute(
            "SELECT id,heading,text FROM passages WHERE document_id=? ORDER BY ordinal",
            (doc["id"],),
        ):
            done = bool(state["state"]["reading"].get(f"read:{p['id']}"))
            yield _activity(
                "paper", uid, doc["content_hash"], f"read:{p['id']}",
                f"阅读：{paper['title']} · {p['heading']}",
                "completed" if done else "pending", "recorded" if done else "none",
                f"{url}&focus={quote(p['id'], safe='')}",
                detail="读过的记录不等于掌握。",
                estimated_minutes=max(5, len(p["text"]) // 150), evidence_ids=[p["id"]],
            )
        for key, title in CHECKS:
            answer = state["state"]["answers"].get(key, {})
            status = answer.get("status")
            yield _activity(
                "paper", uid, doc["content_hash"], f"answer:{key}",
                f"理解检查：{paper['title']} · {title}",
                "completed" if status == "answered" else "in_progress" if answer.get("text") else "pending",
                "recorded" if status == "answered" else "none",
                f"{url}&focus={key}",
                detail="回答由用户记录，未经自动判分。",
            )


def _case_activities(conn):
    from app.api.cases import read_session
    from app.assistant.engine import exercises

    row = conn.execute(
        "SELECT id FROM case_sessions WHERE case_id=? ORDER BY updated_at DESC,rowid DESC LIMIT 1",
        (CASE_ID,),
    ).fetchone()
    if not row:
        return
    session = read_session(conn, CASE_ID, row["id"])
    base = f"/cases/{quote(CASE_ID, safe='')}?session={quote(session['id'], safe='')}"
    stale = session["case_version"] != VERSION
    for question in QUESTIONS:
        answer = session["state"]["answers"].get(question["id"])
        correct = bool(answer and answer.get("correct"))
        yield _activity(
            "case", session["id"], session["case_version"], f"question:{question['id']}",
            f"案例理解：{question['question']}",
            "needs_review" if stale else "completed" if correct else "in_progress" if answer else "pending",
            "checked" if correct else "recorded" if answer else "none",
            base, detail="答对固定题目不等于全面掌握。" if correct else "请结合反馈回顾源码。",
        )
    for exercise in exercises(session):
        result = exercise.result
        correct = bool(result and result.get("correct"))
        yield _activity(
            "case", session["id"], session["case_version"], f"practice:{exercise.id}",
            f"案例练习：{exercise.prompt}",
            "needs_review" if stale else "completed" if correct else "in_progress" if result else "pending",
            "checked" if correct else "recorded" if result else "none",
            base, detail="固定练习检查通过，不代表科研复现。" if correct else "请结合反馈重新尝试。",
        )


def _project_activities(conn):
    for snapshot in latest_snapshots(conn):
        sid = snapshot["id"]
        pid = snapshot["project_id"]
        plan = snapshot["plan"]
        url = f"/research/{quote(pid, safe='')}?tab=plans&snapshot={quote(sid, safe='')}"
        for step in plan["steps"]:
            record = step_record(conn, sid, step["id"])
            yield _activity(
                "project", sid, snapshot["snapshot_version"], step["id"],
                f"课题：{plan['title']} · {step['title']}",
                "needs_review" if snapshot["review_status"] == "needs_review" else
                "completed" if record["done"] else "pending",
                "recorded" if record["done"] else "none", url,
                detail=record["outcome"] or "按快照中的验收条件记录产出；不代表科学结论得到验证。",
                evidence_ids=step.get("evidence_ids", []),
                project_id=pid,
            )


def activities(conn, source_kind=None, source_id=None, project_id=None):
    result = []
    for source, factory in (("roadmap", _roadmap_activities), ("paper", _paper_activities),
                            ("case", _case_activities), ("project", _project_activities)):
        if source_kind and source_kind != source:
            continue
        for item in factory(conn):
            if source_id and item["source_id"] != source_id:
                continue
            if project_id and item["project_id"] != project_id:
                continue
            result.append(item)
    order = {"needs_review": 0, "in_progress": 1, "pending": 2, "completed": 3}
    return sorted(result, key=lambda a: (order[a["status"]], a["source_kind"], a["title"], a["id"]))


def overview(conn):
    items = activities(conn)
    counts = {name: sum(a["status"] == name for a in items) for name in
              ("pending", "in_progress", "completed", "needs_review")}
    snapshot_needed = conn.execute(
        "SELECT COUNT(*) FROM research_plan_versions p WHERE p.version=("
        "SELECT MAX(version) FROM research_plan_versions WHERE plan_id=p.plan_id) "
        "AND NOT EXISTS (SELECT 1 FROM research_snapshots s WHERE s.project_id=p.project_id "
        "AND json_extract(s.payload_json,'$.plan.id')=p.plan_id "
        "AND json_extract(s.payload_json,'$.plan.version')=p.version)"
    ).fetchone()[0]
    return {"counts": counts, "next": [a for a in items if a["status"] != "completed"][:8],
            "snapshot_required": snapshot_needed, "total": len(items)}


def failed_case_checks(conn):
    from app.api.cases import read_session
    from app.assistant.engine import exercises

    row = conn.execute(
        "SELECT id FROM case_sessions WHERE case_id=? ORDER BY updated_at DESC,rowid DESC LIMIT 1",
        (CASE_ID,),
    ).fetchone()
    if not row:
        return []
    session = read_session(conn, CASE_ID, row["id"])
    if session["stale"]:
        return []
    failed = []
    for q in QUESTIONS:
        answer = session["state"]["answers"].get(q["id"])
        if answer and not answer.get("correct"):
            failed.append({"key": f"question:{q['id']}", "title": q["question"]})
    for exercise in exercises(session):
        if exercise.result and not exercise.result.get("correct"):
            failed.append({"key": f"practice:{exercise.id}", "title": exercise.prompt})
    return failed
