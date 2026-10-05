"""实体/关系写图：MERGE 幂等；标签白名单防注入。"""
from app.db.neo4j_client import get_driver

_LABELS = {"paper", "concept", "method", "dataset", "benchmark", "resource", "author"}
_RELS = {
    "CITES", "PROPOSES", "USES", "EVALUATES_ON", "IMPROVES_ON",
    "COMPARED_WITH", "PREREQUISITE_OF", "HAS_RESOURCE", "SUBTOPIC_OF", "MENTIONS",
}


def validate_entity_type(etype: str) -> None:
    if etype.lower() not in _LABELS:
        raise ValueError(f"invalid entity type: {etype}")


def validate_relation_type(rel_type: str) -> None:
    if rel_type.upper() not in _RELS:
        raise ValueError(f"invalid relation type: {rel_type}")


def merge_entity(etype: str, uid: str, name: str) -> None:
    validate_entity_type(etype)
    label = etype.capitalize()
    with get_driver().session() as session:
        session.run(
            f"MERGE (n:Entity {{uid: $uid}}) SET n:`{label}`, n.name = coalesce(n.name, $name), n.type = $type",
            uid=uid, name=name, type=etype.lower(),
        )


def merge_relation(rel_type: str, src_uid: str, dst_uid: str) -> None:
    validate_relation_type(rel_type)
    with get_driver().session() as session:
        session.run(
            f"MERGE (s:Entity {{uid: $src}}) MERGE (d:Entity {{uid: $dst}}) "
            f"MERGE (s)-[r:`{rel_type.upper()}`]->(d)",
            src=src_uid, dst=dst_uid,
        )


def find_entity_uid_by_name(conn, name: str, entity_type: str | None = None) -> str | None:
    if entity_type:
        row = conn.execute(
            "SELECT uid FROM entity_vectors WHERE lower(name)=lower(?) AND uid LIKE ?",
            (name, f"{entity_type.lower()}:%"),
        ).fetchone()
    else:
        row = conn.execute("SELECT uid FROM entity_vectors WHERE lower(name)=lower(?)", (name,)).fetchone()
    return row["uid"] if row else None

def promote_auto_merged(conn, paper_uid=None) -> int:
    from app.db.proposals import list_proposals, update_status

    n = 0
    for p in list_proposals(conn, status="auto_merged", kind="entity"):
        if paper_uid and p["paper_uid"] != paper_uid:
            continue
        merge_entity(p["payload"]["type"], p["payload"]["align"]["match_uid"], p["payload"]["name"])
        merge_relation("MENTIONS", p["paper_uid"], p["payload"]["align"]["match_uid"])
        update_status(conn, p["id"], "approved")
        n += 1
    return n

def set_relation_quality(conn,proposal,status):
    from app.pipeline.extract import canonical_uid
    payload=proposal['payload']
    rel=payload['rel_type']
    validate_relation_type(rel)
    src=payload.get('src_uid') or find_entity_uid_by_name(conn,payload['src_name'],payload['src_type']) or canonical_uid(payload['src_type'],payload['src_name'])
    dst=payload.get('dst_uid') or find_entity_uid_by_name(conn,payload['dst_name'],payload['dst_type']) or canonical_uid(payload['dst_type'],payload['dst_name'])
    with get_driver().session() as session:
        session.run(f'MATCH (s:Entity {{uid:$src}})-[r:`{rel}`]->(d:Entity {{uid:$dst}}) SET r.quality_status=$status, r.knowledge_id=$kid, r.passage_id=$pid',
                    src=src,dst=dst,status=status,kid=proposal['id'],pid=payload.get('passage_id'))
