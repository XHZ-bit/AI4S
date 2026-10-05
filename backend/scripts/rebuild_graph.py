"""Rebuild Neo4j from approved SQLite records without retaining old graph data."""
import json

from app.db.neo4j_client import ensure_constraints, get_driver, merge_paper
from app.db.proposals import list_proposals
from app.db.sqlite import connect
from app.graphsvc.entities import merge_entity, merge_relation, find_entity_uid_by_name
from app.pipeline.extract import canonical_uid


def dedupe_proposals(conn) -> int:
    rows = conn.execute(
        "SELECT id, paper_uid, kind, payload_json, status FROM extraction_proposals ORDER BY id"
    ).fetchall()
    groups: dict[tuple, list] = {}
    for row in rows:
        key = (row["paper_uid"], row["kind"], json.dumps(json.loads(row["payload_json"]), sort_keys=True))
        groups.setdefault(key, []).append(row)
    changed = 0
    priority = {"approved": 0, "auto_merged": 1, "pending": 2, "rejected": 3, "duplicate": 4}
    for group in groups.values():
        if len(group) < 2:
            continue
        keep = min(group, key=lambda r: (priority.get(r["status"], 9), r["id"]))
        for row in group:
            if row["id"] != keep["id"] and row["status"] != "duplicate":
                conn.execute("UPDATE extraction_proposals SET status='duplicate' WHERE id=?", (row["id"],))
                changed += 1
    conn.commit()
    return changed


def rebuild() -> dict:
    conn = connect()
    driver = get_driver()
    duplicate_rows = dedupe_proposals(conn)

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
    ensure_constraints()

    papers = conn.execute("SELECT * FROM papers ORDER BY created_at").fetchall()
    for row in papers:
        merge_paper(dict(row))

    approved = list_proposals(conn, status="approved")
    for proposal in approved:
        if proposal["kind"] != "entity":
            continue
        payload = proposal["payload"]
        entity_type = payload["type"]
        name = payload["name"]
        uid = payload.get("canonical_uid") or find_entity_uid_by_name(conn, name, entity_type) or canonical_uid(entity_type, name)
        merge_entity(entity_type, uid, name)
        merge_relation("MENTIONS", proposal["paper_uid"], uid)

    for proposal in approved:
        if proposal["kind"] != "relation":
            continue
        payload = proposal["payload"]
        src_type = payload.get("src_type", "concept")
        dst_type = payload.get("dst_type", "concept")
        src_uid = find_entity_uid_by_name(conn, payload["src_name"], src_type) or canonical_uid(src_type, payload["src_name"])
        dst_uid = find_entity_uid_by_name(conn, payload["dst_name"], dst_type) or canonical_uid(dst_type, payload["dst_name"])
        merge_entity(src_type, src_uid, payload["src_name"])
        merge_entity(dst_type, dst_uid, payload["dst_name"])
        merge_relation(payload["rel_type"], src_uid, dst_uid)
        merge_relation("MENTIONS", proposal["paper_uid"], src_uid)
        merge_relation("MENTIONS", proposal["paper_uid"], dst_uid)

    with driver.session() as session:
        node_count = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        duplicate_uids = session.run(
            "MATCH (n:Entity) WITH n.uid AS uid, count(*) AS c WHERE c > 1 RETURN count(*) AS c"
        ).single()["c"]
        incomplete = session.run(
            "MATCH (n:Entity) WHERE n.name IS NULL OR n.type IS NULL RETURN count(n) AS c"
        ).single()["c"]
    driver.close()
    conn.close()
    return {
        "deduplicated_proposals": duplicate_rows,
        "nodes": node_count,
        "relationships": rel_count,
        "duplicate_uid_groups": duplicate_uids,
        "incomplete_nodes": incomplete,
    }


if __name__ == "__main__":
    print(json.dumps(rebuild(), ensure_ascii=False))