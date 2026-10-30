"""Read-only projection of existing work into one local execution view."""

import hashlib
import json

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
              *, detail="", estimated_minutes=None, evidence_ids=None, project_id=None,
              item_uid=None):
    return {
        "id": f"{kind}:{source_id}:{item_id}", "source_kind": kind,
        "source_id": str(source_id), "source_version": version,
        "item_id": str(item_id), "title": title, "status": status,
        "evidence_level": evidence_level, "url": url, "detail": detail,
        "estimated_minutes": estimated_minutes, "evidence_ids": evidence_ids or [],
        "project_id": project_id,
        "item_uid": item_uid,
    }


def _roadmap_activities(conn, source=None):
    rows = conn.execute(
        "SELECT id FROM roadmaps WHERE id NOT IN (SELECT parent_id FROM workflow_roadmap_lineage) AND (? IS NULL OR id=?) ORDER BY id DESC", (source, source)
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
                    item_uid=item.uid,
                )


def _paper_activities(conn, source=None):
    rows = conn.execute("SELECT uid,title FROM papers WHERE (? IS NULL OR uid=?) ORDER BY created_at DESC,uid DESC", (source, source)).fetchall()
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


def _case_activities(conn, source=None):
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


def _project_activities(conn, source=None):
    from app.research.audit import project_audit

    impacted = {}
    for snapshot in latest_snapshots(conn):
        sid = snapshot["id"]
        pid = snapshot["project_id"]
        if source and pid != source:
            continue
        if pid not in impacted:
            exists = conn.execute("SELECT 1 FROM research_project_versions WHERE project_id=? LIMIT 1", (pid,)).fetchone()
            impacted[pid] = ({sid for issue in project_audit(conn, pid)["issues"]
                              if issue["severity"] == "blocking"
                              for sid in issue["affected_snapshot_ids"]} if exists else set())
        plan = snapshot["plan"]
        url = f"/research/{quote(pid, safe='')}?tab=plans&snapshot={quote(sid, safe='')}"
        for step in plan["steps"]:
            record = step_record(conn, sid, step["id"])
            yield _activity(
                "project", sid, snapshot["snapshot_version"], step["id"],
                f"课题：{plan['title']} · {step['title']}",
                "needs_review" if snapshot["review_status"] == "needs_review" or sid in impacted[pid] else
                "completed" if record["done"] else "pending",
                "recorded" if record["done"] else "none", url,
                detail=record["outcome"] or "按快照中的验收条件记录产出；不代表科学结论得到验证。",
                evidence_ids=step.get("evidence_ids", []),
                project_id=pid,
            )


def activities(conn, source_kind=None, source_id=None, project_id=None):
    from app.db.projections import activity_page
    return activity_page(conn, source_kind, source_id, project_id, limit=-1)['items']


def overview(conn):
    from app.db.projections import activity_page
    first = activity_page(conn, limit=8)
    names = ['needs_review', 'in_progress', 'pending', 'completed']
    counts = dict.fromkeys(names, 0)
    for row in conn.execute('SELECT status_order,COUNT(*) FROM activity_projection GROUP BY status_order'):
        counts[names[row[0]]] = row[1]
    snapshot_needed = conn.execute(
        "SELECT COUNT(*) FROM research_plan_versions p WHERE p.version=("
        "SELECT MAX(version) FROM research_plan_versions WHERE plan_id=p.plan_id) "
        "AND NOT EXISTS (SELECT 1 FROM research_snapshots s WHERE s.project_id=p.project_id "
        "AND json_extract(s.payload_json,'$.plan.id')=p.plan_id "
        "AND json_extract(s.payload_json,'$.plan.version')=p.version)"
    ).fetchone()[0]
    return {"counts": counts, "next": [a for a in first['items'] if a["status"] != "completed"],
            "snapshot_required": snapshot_needed, "total": first['total']}


def recommendations(conn):
    """Rank current actions by explicit, deterministic rules without changing records."""
    items = activities(conn)
    failed = failed_case_checks(conn)
    confirmed = sorted(r["concept_uid"] for r in conn.execute(
        "SELECT concept_uid FROM workflow_mastery WHERE confirmed=1"
    ))
    suggestions = []
    review_groups = {}
    for item in items:
        if item["status"] == "needs_review":
            review_groups.setdefault((item["source_kind"], item["source_id"]), []).append(item)
    for (source_kind, source_id), group in sorted(review_groups.items()):
        first = group[0]
        count = len(group)
        suggestions.append({"id": f"check:{source_kind}:{source_id}", "kind": "source_review",
                            "title": f"检查依据：{first['title']}",
                            "reason": f"同一来源有 {count} 项活动待复核；原有完成记录保留。",
                            "url": first["url"], "source_ids": [item["id"] for item in group],
                            "priority_score": 95, "priority_reason": "待复核活动需先检查来源",
                            "related_activity_count": count})
    for check in failed:
        suggestions.append({"id": f"review:{check['key']}", "kind": "practice_review",
                            "title": f"复习并重试：{check['title']}",
                            "reason": "最近一次固定案例检查未通过；这只反映题目结果。",
                            "url": check["url"], "source_ids": [check["key"]],
                            "priority_score": 80, "priority_reason": "最近一次固定检查未通过",
                            "related_activity_count": 1})
    rows = conn.execute(
        "SELECT id,profile_json FROM roadmaps WHERE id NOT IN "
        "(SELECT parent_id FROM workflow_roadmap_lineage) ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        route = get_roadmap(conn, row["id"])
        saved = json.loads(row["profile_json"])
        reasons = []
        if route.stale:
            reasons.append("路线来源版本或关系已变化")
        if sorted(saved.get("known_concepts", [])) != confirmed:
            reasons.append("已确认掌握记录与生成路线时不同")
        if failed:
            reasons.append("最近一次固定案例练习有未通过项")
        if reasons:
            score = 70 if route.stale else 60
            suggestions.append({"id": f"replan:{row['id']}", "kind": "replan_preview",
                                "title": "预览正式路线调整", "reason": "；".join(reasons),
                                "url": f"/roadmap?id={row['id']}",
                                "source_ids": [str(row["id"]), *[x["key"] for x in failed]],
                                "priority_score": score,
                                "priority_reason": "路线来源已变化" if route.stale else "掌握记录或练习反馈已变化",
                                "related_activity_count": 1})
    active_groups = {}
    for item in items:
        if item["status"] in ("pending", "in_progress"):
            active_groups.setdefault((item["source_kind"], item["source_id"]), []).append(item)
    for (source_kind, source_id), group in sorted(active_groups.items()):
        first = min(group, key=lambda item: (item["status"] != "in_progress", item["id"]))
        in_progress = first["status"] == "in_progress"
        suggestions.append({"id": f"continue:{first['id']}", "kind": "continue_activity",
                            "title": f"继续执行：{first['title']}",
                            "reason": "已有部分记录，可从此处继续。" if in_progress else
                                      "这项活动尚未完成，可从原页面开始。",
                            "url": first["url"], "source_ids": [first["id"]],
                            "priority_score": 50 if in_progress else 30,
                            "priority_reason": "已有部分记录" if in_progress else "尚无完成记录",
                            "related_activity_count": len(group),
                            "estimated_minutes": first["estimated_minutes"]})
    suggestions.sort(key=lambda item: (-item["priority_score"], item["kind"], item["id"]))
    for rank, suggestion in enumerate(suggestions, 1):
        suggestion["rank"] = rank
    digest = hashlib.sha256(json.dumps([confirmed, failed, items, suggestions],
                                     ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {"contract_version": "workflow-recommendations-v1", "input_fingerprint": digest,
            "items": suggestions[:20], "total": len(suggestions), "truncated": len(suggestions) > 20,
            "ranking_rule_version": "workflow-priority-1",
            "notice": "固定规则按待复核、练习失败、路线变化、继续执行排序；只使用当前记录，不推断掌握或自动保存路线。"}


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
    url = f"/cases/{quote(CASE_ID, safe='')}?session={quote(session['id'], safe='')}"
    for q in QUESTIONS:
        answer = session["state"]["answers"].get(q["id"])
        if answer and not answer.get("correct"):
            failed.append({"key": f"question:{q['id']}", "title": q["question"], "url": url})
    for exercise in exercises(session):
        if exercise.result and not exercise.result.get("correct"):
            failed.append({"key": f"practice:{exercise.id}", "title": exercise.prompt, "url": url})
    return failed
