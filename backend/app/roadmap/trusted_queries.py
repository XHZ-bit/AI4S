"""Read roadmap inputs from the evidence ledger, the source of truth for review."""

import json

from app.pipeline.extract import canonical_uid


def _relations(conn, status):
    for row in conn.execute(
        "SELECT p.payload_json,k.id,k.paper_uid,k.passage_id,k.layer,pa.text "
        "FROM knowledge k JOIN extraction_proposals p ON p.id=k.id "
        "LEFT JOIN passages pa ON pa.id=k.passage_id "
        "WHERE k.status=? AND p.kind='relation'", (status,)
    ):
        payload = json.loads(row["payload_json"])
        if not all(payload.get(k) for k in ("src_type", "src_name", "dst_type", "dst_name", "rel_type")):
            continue
        yield row, payload


def _uid(payload, side):
    return payload.get(f"{side}_uid") or canonical_uid(payload[f"{side}_type"], payload[f"{side}_name"])


def list_targets(conn, q="", status="human_verified", limit=20):
    found = {}
    for _, p in _relations(conn, status):
        for side in ("src", "dst"):
            if p[f"{side}_type"] not in ("concept", "method"):
                continue
            uid, name = _uid(p, side), p[f"{side}_name"]
            if q.casefold() in f"{uid} {name}".casefold():
                found[uid] = {"uid": uid, "name": name, "type": p[f"{side}_type"]}
    return sorted(found.values(), key=lambda x: (x["name"].casefold(), x["uid"]))[:limit]


def resolve_target(conn, name, status="human_verified"):
    matches = [x["uid"] for x in list_targets(conn, status=status, limit=10000)
               if x["uid"].casefold() == name.casefold() or x["name"].casefold() == name.casefold()]
    return matches[0] if len(set(matches)) == 1 else None


def get_prerequisite_edges(conn, status="human_verified"):
    return sorted({(_uid(p, "src"), _uid(p, "dst")) for row, p in _relations(conn, status)
                   if p["rel_type"] == "PREREQUISITE_OF" and row["layer"] == "teaching"
                   and row["passage_id"] and row["text"] is not None})


def get_papers_for_concept(conn, concept_uid, status="human_verified"):
    grouped = {}
    for row, p in _relations(conn, status):
        if p["rel_type"] not in ("PROPOSES", "USES", "MENTIONS") or _uid(p, "dst") != concept_uid:
            continue
        if p["src_type"] != "paper" or not row["passage_id"] or row["text"] is None:
            continue
        paper = conn.execute("SELECT uid,title,year,code_url FROM papers WHERE uid=?", (row["paper_uid"],)).fetchone()
        if not paper or (p.get("src_uid") and p["src_uid"] != paper["uid"]) or (
            not p.get("src_uid") and p["src_name"].casefold() != paper["title"].casefold()
        ):
            continue
        item = grouped.setdefault(paper["uid"], {**dict(paper), "has_resource": bool(paper["code_url"]),
                                                   "evidence_ids": [], "knowledge_ids": []})
        item["evidence_ids"].append(row["passage_id"])
        item["knowledge_ids"].append(row["id"])
    return list(grouped.values())
