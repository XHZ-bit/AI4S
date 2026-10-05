"""Bounded durable job records; execution remains local to a single process."""

import json
import logging
from threading import BoundedSemaphore

from app.db.sqlite import connect
from app.db.workspace import stage
from app.tasks import submit_task

logger = logging.getLogger(__name__)
_slots = BoundedSemaphore(24)


def enqueue(kind, params):
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
        row = conn.execute(
            "SELECT id FROM tasks WHERE type=? AND params_json=? AND status IN ('queued','running')",
            (kind, encoded),
        ).fetchone()
        if row:
            conn.rollback()
            _slots.release()
            return row["id"]
        tid = conn.execute(
            "INSERT INTO tasks(type,params_json,status) VALUES(?,?,'queued')",
            (kind, encoded),
        ).lastrowid
        conn.commit()
    except Exception:
        _slots.release()
        raise
    finally:
        conn.close()
    try:
        submit_task(run, tid)
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

    if not _slots.acquire(blocking=False):
        raise RuntimeError("任务队列已满，请稍后重试")
    try:
        submit_task(run_research, task_id)
    except Exception:
        _slots.release()
        raise


def run_research(task_id: str) -> None:
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
                        code="task_failed", message=str(exc), retryable=False
                    ),
                )
        except Exception:
            logger.exception("Could not persist research task failure %s", task_id)
    finally:
        conn.close()
        _slots.release()


def run(tid):
    try:
        conn = connect()
    except Exception:
        _slots.release()
        logger.exception("Could not open task database")
        return
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        params = json.loads(row["params_json"])
        conn.execute(
            "UPDATE tasks SET status='running',updated_at=datetime('now') WHERE id=?",
            (tid,),
        )
        conn.commit()
        if row["type"] in ("ingest", "extract", "download"):
            uid = params["uid"]
            if row["type"] == "download":
                from app.fulltext import fetch_pdf

                fetch_pdf(conn, uid)
            if row["type"] in ("ingest", "download"):
                from app.api.papers import process_saved_pdf

                process_saved_pdf(conn, uid)
            from app.db.sqlite import get_paper
            from app.pipeline.evidence import extract_document

            stage(conn, uid, "extract", "running")
            try:
                result = extract_document(conn, get_paper(conn, uid))
                stage(conn, uid, "extract", "done")
            except Exception as exc:
                stage(conn, uid, "extract", "failed", str(exc))
                raise
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

            result = run_collect(**params, task_id=tid)
        else:
            raise ValueError("unsupported task type")
        if params.get("uid"):
            result["warnings"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT stage,error FROM pipeline_stages WHERE paper_uid=? AND status='failed'",
                    (params["uid"],),
                )
            ]
        conn.execute(
            "UPDATE tasks SET status='done',result_json=?,error=NULL,updated_at=datetime('now') WHERE id=?",
            (json.dumps(result, ensure_ascii=False), tid),
        )
        conn.commit()
    except Exception as exc:
        logger.exception("Task %s failed", tid)
        conn.execute(
            "UPDATE tasks SET status='failed',error=?,updated_at=datetime('now') WHERE id=?",
            (str(exc), tid),
        )
        conn.commit()
    finally:
        conn.close()
        _slots.release()
