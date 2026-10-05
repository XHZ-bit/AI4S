"""Full-text evidence extraction with bounded asynchronous jobs."""

from contextlib import closing
from fastapi import APIRouter, HTTPException
from app.db.sqlite import connect, get_paper
from app.pipeline.evidence import extract_document

router = APIRouter(tags=["extract"])


def _connect():
    return connect()


def _run_extraction(conn, uid):
    paper = get_paper(conn, uid)
    if paper is None:
        raise HTTPException(404, "paper not found")
    return extract_document(conn, paper)


@router.post("/api/papers/{uid}/extract")
def extract(uid: str):
    with closing(_connect()) as conn:
        return _run_extraction(conn, uid)


@router.post("/api/papers/{uid}/extract-async", status_code=202)
def extract_async(uid: str):
    from app.jobs import enqueue

    with closing(_connect()) as conn:
        if not get_paper(conn, uid):
            raise HTTPException(404, "paper not found")
    try:
        return {"task_id": enqueue("extract", {"uid": uid}), "status": "queued"}
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.get("/api/extract/{task_id}")
def extract_status(task_id: int):
    from app.api.learning import task

    return task(task_id)
