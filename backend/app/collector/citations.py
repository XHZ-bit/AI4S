"""引用链回填：collect 完成后按 arXiv ID 拉取 Semantic Scholar 引用并入图。"""

import logging
import sqlite3

import httpx

from app.collector.s2 import fetch_citations
from app.db.neo4j_client import merge_cites_batch

logger = logging.getLogger(__name__)


def backfill_citations(conn: sqlite3.Connection, uids: list[str]) -> int:
    """逐篇拉取引用并批量 merge CITES 边，返回新增边数。

    无 arXiv ID 的论文跳过；单篇失败记 warning 不中断整批。
    """
    added = 0
    with httpx.Client() as client:
        for uid in uids:
            row = conn.execute("SELECT arxiv_id FROM papers WHERE uid=?", (uid,)).fetchone()
            if row is None or not row["arxiv_id"]:
                continue
            try:
                refs = fetch_citations(client, row["arxiv_id"])
            except Exception as exc:  # noqa: BLE001 -- 单篇失败不应中断整批回填
                # 引用回填是尽力而为的增强步骤，任何单篇失败都不应让采集任务失败
                logger.warning("citation fetch failed for %s: %s", uid, exc)
                continue
            merge_cites_batch([(uid, ref) for ref in refs])
            added += len(refs)
    return added
