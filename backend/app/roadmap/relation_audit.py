"""Mechanical diagnosis of source-backed knowledge relations, without publication."""

from __future__ import annotations

import hashlib
import json

from app.pipeline.evidence import ENDPOINTS
from app.pipeline.extract import canonical_uid

RULE_VERSION = "relation-audit-1"
ACTIVE = ("candidate", "auto_checked", "demo_curated", "human_verified")


def _uid(payload, side):
    name = payload.get(f"{side}_name")
    kind = payload.get(f"{side}_type")
    return payload.get(f"{side}_uid") or (canonical_uid(kind, name) if name and kind else None)


def relation_audit(conn) -> dict:
    rows = [dict(row) for row in conn.execute(
        "SELECT k.id,k.paper_uid,k.document_id,k.passage_id,k.quote,k.start_offset,"
        "k.end_offset,k.layer,k.status,p.kind,p.payload_json,pa.text,pa.document_id "
        "AS passage_document_id,d.paper_uid AS document_paper_uid "
        "FROM knowledge k LEFT JOIN extraction_proposals p ON p.id=k.id "
        "LEFT JOIN passages pa ON pa.id=k.passage_id "
        "LEFT JOIN documents d ON d.id=k.document_id "
        "WHERE k.status IN (?,?,?,?) ORDER BY k.id", ACTIVE
    )]
    issues = []
    edges = []
    aliases = {}

    def add(code, ids, detail):
        ids = sorted(set(ids))
        key = json.dumps([code, ids], ensure_ascii=False)
        issues.append(dict(id=hashlib.sha256(key.encode()).hexdigest()[:16],
                           code=code, relation_ids=ids, detail=detail))

    for row in rows:
        rid = row["id"]
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (ValueError, TypeError):
            payload = {}
        allowed = ENDPOINTS.get(payload.get("rel_type"))
        if (row["kind"] != "relation" or not allowed
                or payload.get("src_type") not in allowed[0]
                or payload.get("dst_type") not in allowed[1]
                or not all(payload.get(key) for key in ("src_name", "dst_name"))):
            add("invalid_structure", [rid], "关系类型或端点结构不合法。")
            continue
        if (row["document_id"] is None or row["document_paper_uid"] != row["paper_uid"]
                or row["passage_document_id"] != row["document_id"]):
            add("source_mismatch", [rid], "文档、论文与原文片段不属于同一来源。")
        text, quote = row["text"], row["quote"]
        start, end = row["start_offset"], row["end_offset"]
        if (text is None or not quote or start is None or end is None
                or start < 0 or end <= start or text[start:end] != quote):
            add("quote_mismatch", [rid], "引文无法按原始偏移在来源片段中定位。")
        src, dst = _uid(payload, "src"), _uid(payload, "dst")
        if src == dst:
            add("self_relation", [rid], "关系的两个端点解析到同一实体。")
        for side, uid in (("src", src), ("dst", dst)):
            label = (payload[f"{side}_type"], " ".join(payload[f"{side}_name"].casefold().split()))
            aliases.setdefault(label, {}).setdefault(uid, set()).add(rid)
        if payload.get("rel_type") == "PREREQUISITE_OF" and row["layer"] == "teaching" and src != dst:
            edges.append((src, dst, rid))

    for (kind, name), by_uid in aliases.items():
        if len(by_uid) > 1:
            add("ambiguous_alias", [rid for ids in by_uid.values() for rid in ids],
                f"同一 {kind} 名称“{name}”对应多个实体标识，目标解析可能歧义。")

    graph = {}
    for src, dst, rid in edges:
        graph.setdefault(src, []).append((dst, rid))

    # A path back to the start makes an edge part of a directed cycle.
    cyclic = set()
    for src, dst, rid in edges:
        pending = [dst]
        visited = set()
        while pending:
            node = pending.pop()
            if node == src:
                cyclic.add(rid)
                break
            if node in visited:
                continue
            visited.add(node)
            pending.extend(neighbor for neighbor, _ in graph.get(node, ()))
    if cyclic:
        add("prerequisite_cycle", cyclic, "先修关系形成有向环，不能据此生成学习顺序。")

    issues.sort(key=lambda item: (item["code"], item["id"]))
    digest = hashlib.sha256(json.dumps([RULE_VERSION, rows], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(contract_version="relation-audit-v1", rule_version=RULE_VERSION,
                input_fingerprint=digest, checked_relations=len(rows), issues=issues,
                mechanically_clean=not issues,
                notice="结构、原文定位和环检测通过不代表关系在教学或科研语义上正确；状态不会自动升级。")
