"""实体对齐：新候选实体名 embedding 与图内实体向量余弦三级分流（设计 §4③）。"""
import math

from app.db.proposals import all_entity_vectors, list_proposals, update_status

AUTO_MERGE_AT = 0.85
MANUAL_AT = 0.60


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def find_match(conn, name: str, embedding: list[float], entity_type: str | None = None) -> dict:
    best_uid, best_name, best_sim = None, None, 0.0
    for row in all_entity_vectors(conn):
        if entity_type and not row["uid"].startswith(f"{entity_type.lower()}:"):
            continue
        sim = cosine(embedding, row["embedding"])
        if sim > best_sim:
            best_uid, best_name, best_sim = row["uid"], row["name"], sim
    if best_sim >= AUTO_MERGE_AT and (best_name or "").casefold() == name.casefold():
        return {"decision": "auto_merge", "match_uid": best_uid, "match_name": best_name, "similarity": best_sim}
    if best_sim >= MANUAL_AT:
        return {"decision": "manual", "match_uid": best_uid, "match_name": best_name, "similarity": best_sim}
    return {"decision": "new", "match_uid": None, "match_name": None, "similarity": best_sim}


def align_pending_entities(conn, paper_uid=None) -> list[dict]:
    from app.pipeline.extract import canonical_uid

    manual = []
    for p in list_proposals(conn, status="pending", kind="entity"):
        if paper_uid and p["paper_uid"] != paper_uid:
            continue
        if not p.get("embedding"):
            continue
        decision = find_match(conn, p["payload"]["name"], p["embedding"], p["payload"]["type"])
        payload = {**p["payload"], "align": decision}
        if decision["decision"] == "auto_merge":
            update_status(conn, p["id"], "auto_merged", edited_payload=payload)
        else:
            if decision["decision"] == "new":
                payload["canonical_uid"] = canonical_uid(p["payload"]["type"], p["payload"]["name"])
            update_status(conn, p["id"], "pending", edited_payload=payload)
            manual.append({**p, "payload": payload})
    return manual
