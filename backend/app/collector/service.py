"""采集编排服务：同步执行 / 后台线程池执行，任务状态落库 tasks 表。"""

import json
import logging

import httpx

from app.collector.arxiv import fetch_topic
from app.collector.citations import backfill_citations
from app.db.neo4j_client import merge_paper
from app.db.sqlite import connect, upsert_paper
from app.search.service import index_paper

logger = logging.getLogger(__name__)


def _connect():
    """获取 sqlite 连接。独立函数便于测试 monkeypatch 与 api 层复用。"""
    return connect()


def run_collect(
    keywords: list[str],
    categories: list[str],
    start_year: int,
    max_results: int,
    task_id: int | None = None,
) -> dict:
    """执行一次采集：抓 arXiv -> upsert sqlite -> merge neo4j。

    task_id 为 None 时新建任务记录（直接调用场景）；
    由 run_collect_async 调用时传入已建记录的 id，避免一个请求产生两条 task 记录。
    """
    conn = _connect()
    if task_id is None:
        task_id = conn.execute(
            "INSERT INTO tasks (type, params_json) VALUES ('collect', ?)",
            (json.dumps({"keywords": keywords, "categories": categories}, ensure_ascii=False),),
        ).lastrowid
        conn.commit()
    try:
        with httpx.Client() as client:
            docs = fetch_topic(client, keywords, categories, start_year, max_results)
        uids = [upsert_paper(conn, doc.model_dump()) for doc in docs]
        for uid, doc in zip(uids, docs, strict=True):
            merge_paper(doc.model_dump())
            try:
                index_paper(conn, uid, f"{doc.title}\n{doc.abstract}")
            except Exception as exc:
                logger.warning("paper embedding failed for %s: %s", uid, exc)
        backfill_citations(conn, uids)
        conn.execute(
            "UPDATE tasks SET status='done', updated_at=datetime('now') WHERE id=?", (task_id,)
        )
        conn.commit()
        return {"collected": len(uids), "uids": uids}
    except Exception as exc:
        conn.execute(
            "UPDATE tasks SET status='failed', error=?, updated_at=datetime('now') WHERE id=?",
            (str(exc), task_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()


def get_task_status(task_id: int) -> dict | None:
    """查询采集任务状态；不存在返回 None。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, status, error FROM tasks WHERE id=? AND type='collect'", (task_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def run_collect_async(**kw) -> int:
    from app.jobs import enqueue
    return enqueue("collect",kw)
