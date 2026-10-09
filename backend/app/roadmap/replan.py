"""Preview and persist evidence-bound updates without changing route history."""

import hashlib
import json
import uuid
from urllib.parse import quote

from app.db.roadmaps import get_roadmap
from app.models.roadmap import LearnerProfile, RoadmapItem, RoadmapPhase, RoadmapResult
from app.roadmap.generate import generate_roadmap
from app.roadmap.trusted_queries import resolve_target
from app.workflow import failed_case_checks


def _reading_estimate(conn, paper_uid, evidence_ids):
    document_ids = set()
    for evidence_id in evidence_ids:
        row = conn.execute(
            "SELECT d.id FROM passages p JOIN documents d ON d.id=p.document_id "
            "WHERE p.id=? AND d.paper_uid=?", (evidence_id, paper_uid),
        ).fetchone()
        if row:
            document_ids.add(row["id"])
    if not document_ids:
        return None
    return sum(
        max(5, len(p["text"]) // 150)
        for document_id in document_ids
        for p in conn.execute("SELECT text FROM passages WHERE document_id=?", (document_id,))
    ) or None


def _schedule(result, conn, weekly_hours):
    budget = max(60, int(weekly_hours * 60))
    elapsed = 0
    unscheduled = 0
    for phase in result.phases:
        phase_weeks = []
        for item in phase.items:
            if item.kind == "paper" and item.uid:
                item.estimated_minutes = _reading_estimate(conn, item.uid, item.evidence_ids)
                item.source_url = f"/papers/{quote(item.uid, safe='')}?tab=reading"
            elif item.kind == "review":
                item.estimated_minutes = 15
                item.source_url = "/cases/diffusion-policy-intro"
            if item.estimated_minutes is None:
                item.scheduled_week = None
                unscheduled += 1
                continue
            item.scheduled_week = 1 + elapsed // budget
            phase_weeks.extend((item.scheduled_week, 1 + (elapsed + item.estimated_minutes - 1) // budget))
            elapsed += item.estimated_minutes
        if phase_weeks:
            start, end = min(phase_weeks), max(phase_weeks)
            phase.weeks = (f"第 {start} 周" if start == end else f"第 {start}–{end} 周") + "（阅读与练习估算）"
        else:
            phase.weeks = "未排期：缺少时长估算"
    return {"weekly_hours": weekly_hours, "estimated_minutes": elapsed,
            "unscheduled_count": unscheduled}


def _case_review_phase(conn):
    failed = failed_case_checks(conn)
    if not failed:
        return None
    items = []
    for check in failed:
        items.append(RoadmapItem(
            task_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"atlas:review:{check['key']}")),
            kind="review", uid="diffusion-policy-intro", title=f"回顾：{check['title']}",
            reason="最近一次固定案例练习未通过；请查看反馈后重试。",
            evidence="题目检查结果，不等于领域能力评估。", done=False,
        ))
    return RoadmapPhase(phase=0, title="练习反馈", weeks="未排期", items=items)


def build_preview(conn, rid, expected_version):
    previous = get_roadmap(conn, rid)
    if previous.version != expected_version:
        raise ValueError("路线已更新，请刷新后重试")
    row = conn.execute("SELECT profile_json FROM roadmaps WHERE id=?", (rid,)).fetchone()
    saved = LearnerProfile.model_validate_json(row["profile_json"])
    target_uid = saved.target_uid or next(
        (p.title for p in reversed(previous.phases) if p.phase > 0), None
    )
    if not target_uid:
        raise ValueError("旧路线缺少已确认目标，请新建正式路线")
    confirmed = [r["concept_uid"] for r in conn.execute(
        "SELECT concept_uid FROM workflow_mastery WHERE confirmed=1 ORDER BY concept_uid"
    ) if resolve_target(conn, r["concept_uid"], "human_verified") == r["concept_uid"]]
    profile = saved.model_copy(update={"target_uid": target_uid, "known_concepts": confirmed})
    if target_uid in confirmed:
        result = RoadmapResult(goal=saved.goal, phases=[], innovations=[], knowledge_ids=[])
    else:
        result = generate_roadmap(profile, conn, persist=False)
    old_items = {(p.title, i.kind, i.uid): i for p in previous.phases for i in p.items}
    for phase in result.phases:
        for item in phase.items:
            old = old_items.get((phase.title, item.kind, item.uid))
            item.task_id = old.task_id if old and old.task_id else str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"atlas:task:{phase.title}:{item.kind}:{item.uid}"
            ))
            item.done = bool(old and old.done and sorted(old.evidence_ids) == sorted(item.evidence_ids))
    review = _case_review_phase(conn)
    if review:
        result.phases.insert(0, review)
    result.parent_id = rid
    schedule = _schedule(result, conn, saved.weekly_hours)
    source_refs = sorted({eid for p in result.phases for i in p.items for eid in i.evidence_ids})
    passages = [dict(row) for eid in source_refs if (row := conn.execute(
        "SELECT id,document_id,text FROM passages WHERE id=?", (eid,)
    ).fetchone())]
    mastery = [dict(r) for r in conn.execute(
        "SELECT concept_uid,confirmed,version FROM workflow_mastery ORDER BY concept_uid"
    )]
    digest_input = [rid, expected_version, profile.model_dump(), result.model_dump(),
                    mastery, passages, previous.stale]
    fingerprint = hashlib.sha256(json.dumps(
        digest_input, ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()
    return {"roadmap": result.model_dump(), "input_fingerprint": fingerprint,
            "schedule": schedule, "confirmed_concepts": confirmed,
            "removed_phase_count": max(0, len(previous.phases) - len(result.phases))}


def save_replan(conn, rid, expected_version, fingerprint):
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute(
            "SELECT 1 FROM workflow_roadmap_lineage WHERE parent_id=?", (rid,)
        ).fetchone():
            raise ValueError("此路线已生成新版本，请打开最新路线")
        preview = build_preview(conn, rid, expected_version)
        if preview["input_fingerprint"] != fingerprint:
            raise ValueError("路线依据已变化，请重新预览")
        result = preview["roadmap"]
        result["parent_id"] = None  # lineage is stored separately
        cur = conn.execute(
            "INSERT INTO roadmaps(goal,profile_json,result_json) VALUES(?,?,?)",
            (result["goal"], json.dumps({
                "goal": result["goal"], "target_uid": next(
                    (p["title"] for p in reversed(result["phases"]) if p["phase"] > 0),
                    json.loads(conn.execute(
                        "SELECT profile_json FROM roadmaps WHERE id=?", (rid,)
                    ).fetchone()[0]).get("target_uid"),
                ),
                "known_concepts": preview["confirmed_concepts"],
                "weekly_hours": preview["schedule"]["weekly_hours"],
            }, ensure_ascii=False), json.dumps(result, ensure_ascii=False)),
        )
        conn.execute(
            "INSERT INTO workflow_roadmap_lineage(parent_id,child_id) VALUES(?,?)",
            (rid, cur.lastrowid),
        )
        conn.commit()
        return get_roadmap(conn, cur.lastrowid)
    except Exception:
        conn.rollback()
        raise
