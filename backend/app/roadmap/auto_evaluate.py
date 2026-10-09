"""Mechanical gates for source-backed roadmap candidates.

Passing these checks does not validate the scientific or teaching judgment.
"""

import json

from app.models.roadmap import LearnerProfile
from app.pipeline.evidence import ENDPOINTS
from app.roadmap.generate import generate_roadmap
from app.roadmap.graphalgo import topological_sort
from app.roadmap.trusted_queries import get_prerequisite_edges


def evaluate_candidates(conn, target_uid, profiles, status="demo_curated"):
    failures = []
    checked = 0
    rows = conn.execute(
        "SELECT k.*,p.kind,p.payload_json,pa.text,pa.document_id AS source_document "
        "FROM knowledge k JOIN extraction_proposals p ON p.id=k.id "
        "LEFT JOIN passages pa ON pa.id=k.passage_id "
        "WHERE k.status=? AND p.kind='relation' ORDER BY k.id",
        (status,),
    ).fetchall()
    if not rows:
        failures.append("no candidate relations")
    for row in rows:
        kid = row["id"]
        p = json.loads(row["payload_json"])
        allowed = ENDPOINTS.get(p.get("rel_type"))
        if row["kind"] != "relation" or not allowed or p.get("src_type") not in allowed[0] or p.get("dst_type") not in allowed[1]:
            failures.append(f"{kid}: invalid relation structure")
        text = row["text"]
        start, end = row["start_offset"], row["end_offset"]
        if text is None or start is None or end is None or text[start:end] != row["quote"] or not row["quote"].strip():
            failures.append(f"{kid}: evidence quote is not located")
        if row["source_document"] != row["document_id"] or not conn.execute(
            "SELECT 1 FROM documents WHERE id=? AND paper_uid=?",
            (row["document_id"], row["paper_uid"]),
        ).fetchone():
            failures.append(f"{kid}: source document mismatch")
        checked += 1
    edges = get_prerequisite_edges(conn, status)
    nodes = sorted({uid for edge in edges for uid in edge} | {target_uid})
    try:
        topological_sort(nodes, edges)
    except ValueError:
        failures.append("prerequisite cycle")
    routes = {}
    if not failures:
        for name, known in profiles.items():
            try:
                route = generate_roadmap(
                    LearnerProfile(goal=target_uid, target_uid=target_uid, known_concepts=known),
                    conn, status=status, persist=False,
                )
                routes[name] = [phase.title for phase in route.phases]
            except ValueError as exc:
                failures.append(f"{name}: {exc}")
    if len(profiles) > 1 and len({tuple(route) for route in routes.values()}) < 2:
        failures.append("profiles produced no route difference")
    return {"passed": not failures, "checked_relations": checked,
            "checked_profiles": len(routes), "routes": routes, "failures": failures,
            "scope": "mechanical source, graph, and profile checks only"}
