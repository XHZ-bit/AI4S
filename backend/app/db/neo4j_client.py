import logging
import socket
import time
from threading import Lock
from urllib.parse import urlparse
from functools import lru_cache

logger = logging.getLogger(__name__)
_probe_lock = Lock()
_probe_until = 0.0
_probe_uri = ""
_probe_ok = False


def graph_reachable():
    """Fast cached availability probe; do not retry a stopped service per paper."""
    global _probe_until, _probe_uri, _probe_ok
    from app.config import get_settings
    settings = get_settings()
    from app.tenancy import current_user
    if settings.offline_mode or settings.access_mode == "multiuser" or current_user.get():
        return False
    with _probe_lock:
        if _probe_uri == settings.neo4j_uri and time.monotonic() < _probe_until:
            return _probe_ok
        address = urlparse(settings.neo4j_uri)
        try:
            with socket.create_connection((address.hostname or "localhost", address.port or 7687), timeout=0.15):
                pass
            _probe_ok = True
        except OSError:
            _probe_ok = False
        _probe_uri, _probe_until = settings.neo4j_uri, time.monotonic() + 10
        return _probe_ok


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

def get_driver():
    from app.config import get_settings
    if get_settings().access_mode == "multiuser":
        from neo4j.exceptions import ServiceUnavailable
        raise ServiceUnavailable("多人模式尚未启用独立图谱空间")
    if not graph_reachable():
        from neo4j.exceptions import ServiceUnavailable
        raise ServiceUnavailable("Neo4j 未运行，使用工作空间本地图谱")
    return _local_driver()


@lru_cache
def _local_driver():
    from neo4j import GraphDatabase

    from app.config import get_settings

    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=2, connection_acquisition_timeout=3, max_transaction_retry_time=2)


def close_driver() -> None:
    """关闭 Neo4j driver（应用关闭时调用），释放连接池。"""
    try:
        if _local_driver.cache_info().currsize:
            _local_driver().close()
            _local_driver.cache_clear()
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
