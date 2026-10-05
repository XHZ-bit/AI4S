"""图谱查询：节点检索与邻域子图（Cypher 封装）。"""
from app.db.neo4j_client import get_driver


def search_nodes(query: str, node_type: str | None = None, limit: int = 20) -> list[dict]:
    cypher = "MATCH (n:Entity) WHERE toLower(n.name) CONTAINS toLower($q) "
    params: dict = {"q": query, "limit": limit}
    if node_type:
        cypher += "AND n.type = $type "
        params["type"] = node_type
    cypher += "RETURN n.uid AS uid, n.name AS name, n.type AS type LIMIT $limit"
    with get_driver().session() as session:
        return [dict(r) for r in session.run(cypher, **params)]


def overview(limit: int = 100) -> dict:
    limit = max(1, min(int(limit), 500))
    node_query = (
        "MATCH (n:Entity) RETURN n.uid AS uid, n.name AS name, n.type AS type "
        "ORDER BY n.type, n.name LIMIT $limit"
    )
    link_query = (
        "MATCH (s:Entity)-[r]->(d:Entity) "
        "RETURN s.uid AS src, d.uid AS dst, type(r) AS rel_type,r.quality_status AS quality_status,r.passage_id AS passage_id LIMIT $limit"
    )
    with get_driver().session() as session:
        nodes = [dict(r) for r in session.run(node_query, limit=limit) if r["uid"]]
        node_ids = {n["uid"] for n in nodes}
        links = [
            {"source": r["src"], "target": r["dst"], "rel_type": r["rel_type"], "quality_status":r.get("quality_status") or "legacy_unverified", "passage_id":r.get("passage_id")}
            for r in session.run(link_query, limit=limit)
            if r["src"] in node_ids and r["dst"] in node_ids
        ]
    return {"nodes": nodes, "links": links, "truncated": len(nodes) >= limit or len(links) >= limit}


def neighbors(uid: str, depth: int = 1, limit: int = 100) -> dict:
    depth = max(1, min(int(depth), 3))
    limit = max(1, min(int(limit), 500))
    node_query = (
        f"MATCH (root:Entity {{uid: $uid}}) "
        f"OPTIONAL MATCH (root)-[*0..{depth}]-(node:Entity) "
        "RETURN DISTINCT node.uid AS uid, node.name AS name, node.type AS type "
        "LIMIT $limit"
    )
    link_query = (
        f"MATCH path = (root:Entity {{uid: $uid}})-[*1..{depth}]-(other:Entity) "
        "UNWIND relationships(path) AS rel "
        "RETURN DISTINCT startNode(rel).uid AS src, endNode(rel).uid AS dst, "
        "type(rel) AS rel_type,rel.quality_status AS quality_status,rel.passage_id AS passage_id LIMIT $limit"
    )
    with get_driver().session() as session:
        nodes = [dict(r) for r in session.run(node_query, uid=uid, limit=limit) if r["uid"]]
        node_ids = {n["uid"] for n in nodes}
        links = [
            {"source": r["src"], "target": r["dst"], "rel_type": r["rel_type"], "quality_status":r.get("quality_status") or "legacy_unverified", "passage_id":r.get("passage_id")}
            for r in session.run(link_query, uid=uid, limit=limit)
            if r["src"] in node_ids and r["dst"] in node_ids
        ]
    return {"nodes": nodes, "links": links, "truncated": len(nodes) >= limit or len(links) >= limit}