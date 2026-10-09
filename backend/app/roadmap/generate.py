"""Build recommendations from provenance-bound relations; preserve evidence status."""

import json
import re
from contextlib import closing
from app.db.roadmaps import save_roadmap, get_roadmap
from app.db.sqlite import connect
from app.llm.client import chat
from app.models.roadmap import RoadmapResult
from app.roadmap import graphalgo, scoring
from app.roadmap.trusted_queries import (
    get_papers_for_concept,
    get_prerequisite_edges,
    resolve_target,
)
from app.roadmap.prompts import build_target_parse_messages


def _parse_llm_json(raw):
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return json.loads(match.group(1).strip() if match else text)


def _parse_target(goal, conn, status):
    try:
        name = (
            _parse_llm_json(
                chat(build_target_parse_messages(goal), json_mode=True)
            ).get("concept")
            or goal
        )
    except ValueError:
        name = goal
    uid = resolve_target(conn, name, status)
    if not uid:
        raise ValueError("目标无法唯一定位，请搜索并确认目标实体")
    return uid


def _build_skeleton(profile, conn, status):
    target_uid = profile.target_uid or _parse_target(profile.goal, conn, status)
    if not resolve_target(conn, target_uid, status):
        raise ValueError("目标没有可用的来源关系，请先核验资料并选择目标")
    edges = get_prerequisite_edges(conn, status)
    closure = graphalgo.prerequisite_closure([target_uid], edges)
    order = graphalgo.topological_sort(sorted(closure), edges)
    known = set()
    for name in profile.known_concepts:
        uid = resolve_target(conn, name, status)
        if not uid:
            raise ValueError(f"已掌握概念无法唯一定位：{name}")
        known.add(uid)
    order = graphalgo.prune_known(order, known)
    papers = {
        uid: scoring.rank_papers(get_papers_for_concept(conn, uid, status), top_k=2) for uid in order
    }
    if not any(papers.values()):
        raise ValueError(
            "缺少当前证据级别可用的论文与目标关联；请检查资料与关系状态。"
        )
    return {
        "target": target_uid,
        "concept_order": order,
        "concept_papers": papers,
        "experiment_chain": [],
        "innovations": [],
    }


def generate_roadmap(profile, conn=None, *, status="human_verified", persist=True):
    if conn is None:
        with closing(connect()) as owned:
            return generate_roadmap(profile, owned, status=status, persist=persist)
    if status not in ("human_verified", "demo_curated", "auto_checked") or (status != "human_verified" and persist):
        raise ValueError("自动核查或演示预览不得作为正式路线保存")
    skeleton = _build_skeleton(profile, conn, status)
    # Deterministic evidence-bound tasks: text generation cannot add unknown papers.
    phases = []
    kids = set()
    for idx, uid in enumerate(skeleton["concept_order"], 1):
        items = []
        for paper in skeleton["concept_papers"][uid]:
            evidence_ids = paper.get("evidence_ids", [])
            verified_ids = paper.get("knowledge_ids", [])
            if not verified_ids or any(
                not conn.execute(
                    "SELECT 1 FROM knowledge WHERE id=? AND status=?",
                    (kid, status),
                ).fetchone()
                for kid in verified_ids
            ):
                continue
            if not evidence_ids:
                continue
            for pid in evidence_ids:
                if not conn.execute(
                    "SELECT 1 FROM passages WHERE id=?", (pid,)
                ).fetchone():
                    raise ValueError("推荐引用的原文不可用")
            kids.update(paper.get("knowledge_ids", []))
            items.append(
                {
                    "kind": "paper",
                    "uid": paper["uid"],
                    "title": paper["title"],
                    "reason": ("与本阶段知识有关，关联已人工核验。" if status == "human_verified"
                               else "与本阶段知识有关；仅通过自动结构与原文定位检查，教学顺序仍是假设。"),
                    "evidence": "原文证据可定位；不代表论文结论已被独立复现。",
                    "evidence_ids": evidence_ids,
                    "done": False,
                }
            )
        if items:
            phases.append(
                {
                    "phase": idx,
                    "title": uid,
                    "weeks": "未估算时长",
                    "items": items,
                }
            )
    if not phases:
        raise ValueError("没有证据完整的学习任务")
    for row in conn.execute(
        "SELECT id FROM knowledge WHERE status=? AND layer='teaching'", (status,)
    ):
        kids.add(row["id"])
    result = RoadmapResult(
        goal=profile.goal, phases=phases, innovations=[], knowledge_ids=sorted(kids)
    )
    if not persist:
        return result
    rid = save_roadmap(conn, result, profile)
    return get_roadmap(conn, rid)
