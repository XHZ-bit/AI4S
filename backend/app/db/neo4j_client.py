import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


def _paper_merge_query(props: dict) -> tuple[str, dict]:
    params = {"uid": props["uid"]}
    sets = []
    for k in ("title", "abstract", "year", "venue", "source", "code_url", "pdf_url"):
        if props.get(k) is not None:
            params[k] = props[k]
            sets.append(f"p.{k} = ${k}")
    if props.get("title") is not None:
        sets.append("p.name = $title")
    query = "MERGE (p:Entity {uid: $uid}) SET p:Paper, p.type = 'paper'"
    if sets:
        query += " SET " + ", ".join(sets)
    return query, params


def _cites_merge_query(src_uid: str, dst_uid: str) -> tuple[str, dict]:
    query = (
        "MERGE (s:Entity {uid: $src}) "
        "SET s:Paper, s.type = 'paper', s.name = coalesce(s.name, $src) "
        "MERGE (d:Entity {uid: $dst}) "
        "SET d:Paper, d.type = 'paper', d.name = coalesce(d.name, $dst) "
        "MERGE (s)-[r:CITES]->(d)"
    )
    return query, {"src": src_uid, "dst": dst_uid}

@lru_cache
def get_driver():
    from neo4j import GraphDatabase

    from app.config import get_settings

    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


def close_driver() -> None:
    """关闭 Neo4j driver（应用关闭时调用），释放连接池。"""
    try:
        get_driver().close()
    except Exception as exc:  # noqa: BLE001 -- 关闭失败不应阻断进程退出
        logger.warning("neo4j driver close failed: %s", exc)

def ensure_constraints() -> None:
    with get_driver().session() as session:
        session.run(
            "CREATE CONSTRAINT entity_uid IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.uid IS UNIQUE"
        ).consume()


def merge_paper(props: dict) -> None:
    query, params = _paper_merge_query(props)
    with get_driver().session() as session:
        session.run(query, **params)


def merge_cites(src_uid: str, dst_uid: str) -> None:
    query, params = _cites_merge_query(src_uid, dst_uid)
    with get_driver().session() as session:
        session.run(query, **params)

def merge_cites_batch(pairs: list[tuple[str, str]]) -> None:
    """批量 merge CITES 边（UNWIND），减少逐条事务的往返开销。"""
    if not pairs:
        return
    query = (
        "UNWIND $pairs AS pair "
        "MERGE (s:Entity {uid: pair.src}) "
        "SET s:Paper, s.type = 'paper', s.name = coalesce(s.name, pair.src) "
        "MERGE (d:Entity {uid: pair.dst}) "
        "SET d:Paper, d.type = 'paper', d.name = coalesce(d.name, pair.dst) "
        "MERGE (s)-[r:CITES]->(d)"
    )
    params = {"pairs": [{"src": src, "dst": dst} for src, dst in pairs]}
    with get_driver().session() as session:
        session.run(query, **params)
