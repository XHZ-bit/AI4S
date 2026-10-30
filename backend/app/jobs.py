"""Bounded durable job records; execution remains local to a single process."""

import json
import logging
from threading import BoundedSemaphore

from app.db.sqlite import connect
from app.db.workspace import stage
from app.tasks import submit_task
from app.task_control import task_scope, checkpoint, error_code, track_future

logger = logging.getLogger(__name__)
_slots = BoundedSemaphore(24)


def enqueue(kind, params, *, retry_of=None):
    # An idempotent request must still return its existing ID when the pool is full.
    with __import__('contextlib').closing(connect()) as conn:
        encoded = json.dumps(params, ensure_ascii=False, sort_keys=True)
        existing = conn.execute(
            "SELECT id FROM tasks WHERE (retry_of=? AND type=? AND params_json=?) OR "
            "(type=? AND params_json=? AND status IN ('queued','running')) ORDER BY id LIMIT 1",
            (retry_of, kind, encoded, kind, encoded),
        ).fetchone()
        if existing:
            return existing['id']
    return _enqueue(kind, params, retry_of=retry_of)


def _enqueue(kind, params, *, retry_of=None):
    if not _slots.acquire(blocking=False):
        raise RuntimeError("任务队列已满，请稍后重试")
    try:
        conn = connect()
    except Exception:
        _slots.release()
        raise
    try:
        conn.execute("BEGIN IMMEDIATE")
        encoded = json.dumps(params, ensure_ascii=False, sort_keys=True)
        if retry_of is not None:
            prior_retry = conn.execute(
                "SELECT id,type,params_json FROM tasks WHERE retry_of=? ORDER BY id LIMIT 1", (retry_of,),
            ).fetchone()
            if prior_retry:
                if prior_retry["type"] != kind or prior_retry["params_json"] != encoded:
                    raise ValueError("retry key belongs to another task request")
                conn.rollback()
                _slots.release()
                return prior_retry["id"]
        row = conn.execute(
            "SELECT id FROM tasks WHERE type=? AND params_json=? AND status IN ('queued','running')",
            (kind, encoded),
        ).fetchone()
        if row:
            conn.rollback()
            _slots.release()
            return row["id"]
        from app.config import get_settings
        if get_settings().access_mode == 'multiuser':
            active = conn.execute("SELECT (SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')) + "
                                  "(SELECT COUNT(*) FROM research_async_tasks WHERE status IN ('queued','running'))").fetchone()[0]
            if active:
                raise RuntimeError("个人空间已有排队或运行中的任务，请等待完成后重试")
        tid = conn.execute(
            "INSERT INTO tasks(type,params_json,status,retry_of) VALUES(?,?,'queued',?)",
            (kind, encoded, retry_of),
        ).lastrowid
        conn.commit()
    except Exception:
        _slots.release()
        raise
    finally:
        conn.close()
    try:
        future = submit_task(run, tid)
        track_future(f'legacy:{tid}', future, _slots.release)
    except Exception as exc:
        _slots.release()
        conn = connect()
        try:
            conn.execute(
                "UPDATE tasks SET status='failed',error=? WHERE id=?", (str(exc), tid)
            )
            conn.commit()
        finally:
            conn.close()
        raise
    return tid


def enqueue_research_task(task_id: str) -> None:
    """Submit one already-persisted research task to the bounded local executor."""

    from app.config import get_settings
    if get_settings().access_mode == 'multiuser':
        with __import__('contextlib').closing(connect()) as conn:
            active = conn.execute("SELECT (SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')) + "
                                  "(SELECT COUNT(*) FROM research_async_tasks WHERE status IN ('queued','running') AND task_id!=?)",
                                  (task_id,)).fetchone()[0]
            if active:
                raise RuntimeError("个人空间已有排队或运行中的任务，请等待完成后重试")
    if not _slots.acquire(blocking=False):
        raise RuntimeError("任务队列已满，请稍后重试")
    try:
        future = submit_task(run_research, task_id)
        track_future(f'research:{task_id}', future, _slots.release)
    except Exception:
        _slots.release()
        raise


def run_research(task_id: str) -> None:
    with task_scope(f"research:{task_id}"):
        _run_research(task_id)


def _run_research(task_id: str) -> None:
    try:
        conn = connect()
    except Exception:
        _slots.release()
        logger.exception("Could not open research task database")
        return
    try:
        from app.research.service import run_research_task
        from app.research.model_runtime import model_call_scope

        with model_call_scope(task_id):
            checkpoint(conn, "research", 0.05)
            run_research_task(conn, task_id)
    except Exception as exc:
        logger.exception("Research task %s failed", task_id)
        try:
            from app.db import projects as store
            from app.models.research import ErrorDetail, TaskStatus

            current = store.get_task(conn, task_id)
            if current and current.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                store.update_task(
                    conn,
                    task_id,
                    TaskStatus.FAILED,
                    error=ErrorDetail(
                        code=error_code(exc), message=str(exc), retryable=False
                    ),
                )
        except Exception:
            logger.exception("Could not persist research task failure %s", task_id)
    finally:
        conn.close()
        _slots.release()


def run(tid):
    with task_scope(f"legacy:{tid}"):
        _run(tid)


def _run(tid):
    try:
        conn = connect()
    except Exception:
        _slots.release()
        logger.exception("Could not open task database")
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        claimed = conn.execute(
            "UPDATE tasks SET status='running',updated_at=datetime('now') "
            "WHERE id=? AND status='queued'", (tid,),
        ).rowcount
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone() if claimed else None
        conn.commit()
        if row is None:
            return
        params = json.loads(row["params_json"])
        checkpoint(conn, "prepare", 0.05)
        if row["type"] == 'parse_batch':
            from app.api.papers import process_saved_pdf
            completed=[]
            for index,uid in enumerate(params['uids']):
                checkpoint(conn,'parse',0.1+0.8*index/max(1,len(params['uids'])))
                process_saved_pdf(conn,uid)
                completed.append(uid)
            result={'parsed':completed}
        elif row["type"] in ("parse", "ingest", "extract", "download"):
            uid = params["uid"]
            if row["type"] == "download":
                from app.fulltext import fetch_pdf
                from app.api.papers import _data_dir
                if not (_data_dir() / f"{uid}.pdf").is_file():
                    checkpoint(conn, "download", 0.1)
                    fetch_pdf(conn, uid)
            if row["type"] in ("parse", "ingest", "download"):
                from app.api.papers import process_saved_pdf
                checkpoint(conn, "parse", 0.3)
                process_saved_pdf(conn, uid)
            from app.db.sqlite import get_paper
            from app.pipeline.evidence import extract_document
            from app.config import get_settings
            result = {"uid": uid, "parse_status": "parsed"}
            if row['type'] != 'parse' and get_settings().dashscope_api_key:
                checkpoint(conn, "extract", 0.65)
                stage(conn, uid, "extract", "running")
                try:
                    result = extract_document(conn, get_paper(conn, uid))
                    stage(conn, uid, "extract", "done")
                except Exception as exc:
                    stage(conn, uid, "extract", "failed", str(exc))
                    raise
            elif row['type'] == 'extract':
                raise ValueError("模型密钥未配置；已保存原文仍可阅读")
        elif row["type"] == "guide":
            from app.guidance import generate_guide

            result = generate_guide(conn, params["uid"])
        elif row["type"] == "roadmap":
            from app.models.roadmap import LearnerProfile
            from app.roadmap.generate import generate_roadmap

            result = generate_roadmap(
                LearnerProfile.model_validate(params["profile"]), conn
            ).model_dump()
        elif row["type"] == "collect":
            from app.collector.service import run_collect

            result = run_collect(**params, task_id=tid, connection=conn)
        else:
            raise ValueError("unsupported task type")
        checkpoint(conn, "complete", 1.0)
        if params.get("uid"):
            result["warnings"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT stage,error FROM pipeline_stages WHERE paper_uid=? AND status='failed'",
                    (params["uid"],),
                )
            ]
        conn.execute(
            "UPDATE tasks SET status='done',result_json=?,error=NULL,updated_at=datetime('now') "
            "WHERE id=? AND status='running'",
            (json.dumps(result, ensure_ascii=False), tid),
        )
        conn.commit()
    except Exception as exc:
        logger.exception("Task %s failed", tid)
        conn.execute(
            "UPDATE tasks SET status='failed',error=?,updated_at=datetime('now') "
            "WHERE id=? AND status='running'",
            (str(exc), tid),
        )
        conn.execute("UPDATE task_controls SET error_code=? WHERE task_key=?",
                     (error_code(exc), f"legacy:{tid}"))
        conn.commit()
    finally:
        conn.close()
        _slots.release()


def recover_safe_queue(conn):
    """Only untouched local parse work may resume automatically; outbound work is interrupted."""
    rows = conn.execute("SELECT id FROM tasks WHERE status='queued' AND type='parse'").fetchall()
    resumed = 0
    for row in rows:
        if not _slots.acquire(blocking=False):
            conn.execute("UPDATE tasks SET status='failed',error=?,updated_at=datetime('now') WHERE id=? AND status='queued'",
                         ('重启恢复队列已满；原文件保留，请手动重试', row['id']))
            conn.execute("INSERT OR REPLACE INTO task_controls(task_key,error_code) VALUES(?,'restart_capacity')",
                         (f"legacy:{row['id']}",))
            conn.commit()
            continue
        try:
            future = submit_task(run, row['id'])
            track_future(f"legacy:{row['id']}", future, _slots.release)
            resumed += 1
        except Exception:
            _slots.release()
            raise
    return resumed
