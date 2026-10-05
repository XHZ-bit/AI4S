"""Original files are saved before processing; failures can be retried."""

import hashlib
import re
from contextlib import closing
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.db.neo4j_client import merge_paper
from app.db.sqlite import connect, get_paper, upsert_paper
from app.db.workspace import save_document, stage
from app.parser.service import parse_pdf
from app.search.service import index_paper

router = APIRouter(prefix="/api/papers", tags=["papers"])
_MAX_PDF_BYTES = 50 * 1024 * 1024
_UID_RE = re.compile(r"[A-Za-z0-9._-]+")


def _connect():
    return connect()


def _data_dir():
    from app.config import get_settings

    path = Path(get_settings().data_dir) / "pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def process_saved_pdf(conn, uid):
    path = _data_dir() / f"{uid}.pdf"
    stage(conn, uid, "parse", "running")
    try:
        raw = path.read_bytes()
        parsed = parse_pdf(uid, raw, filename=path.name)
        paper = get_paper(conn, uid)
        paper.update(title=parsed.title or paper["title"], abstract=parsed.abstract)
        upsert_paper(conn, paper)
        save_document(conn, uid, parsed, hashlib.sha256(raw).hexdigest(), path.name)
        conn.execute("UPDATE papers SET parse_status='parsed' WHERE uid=?", (uid,))
        conn.commit()
        stage(conn, uid, "parse", "done")
    except Exception as exc:
        stage(conn, uid, "parse", "failed", str(exc))
        raise
    for name, operation in [
        ("graph", lambda: merge_paper(paper)),
        (
            "index",
            lambda: index_paper(conn, uid, parsed.title + "\n" + parsed.abstract),
        ),
    ]:
        stage(conn, uid, name, "running")
        try:
            operation()
            stage(conn, uid, name, "done")
        except Exception as exc:
            stage(conn, uid, name, "failed", str(exc))
    return {"uid": uid, "parse_status": "parsed"}


def _store(file, uid=None):
    if uid and (not _UID_RE.fullmatch(uid) or uid in (".", "..")):
        raise HTTPException(400, "invalid uid")
    raw = file.file.read(_MAX_PDF_BYTES + 1)
    if len(raw) > _MAX_PDF_BYTES:
        raise HTTPException(413, "PDF 超过 50MB 限制")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(400, "文件不是有效的 PDF")
    digest = hashlib.sha256(raw).hexdigest()
    paper_uid = uid or f"upload-{digest[:24]}"
    path = _data_dir() / f"{paper_uid}.pdf"
    with closing(_connect()) as conn:
        from app.storage import save_original

        try:
            save_original(path, raw)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not get_paper(conn, paper_uid):
            upsert_paper(
                conn,
                {
                    "uid": paper_uid,
                    "arxiv_id": None,
                    "title": file.filename or paper_uid,
                    "abstract": "",
                    "authors": [],
                    "year": 0,
                    "venue": None,
                    "categories": [],
                    "published": None,
                    "pdf_url": None,
                    "code_url": None,
                    "source": "upload",
                },
            )
        stage(conn, paper_uid, "file", "done")
    return paper_uid


@router.post("/upload-async", status_code=202)
def upload_async(file: UploadFile):
    from app.jobs import enqueue

    uid = _store(file)
    try:
        return {
            "uid": uid,
            "task_id": enqueue("ingest", {"uid": uid}),
            "parse_status": "queued",
        }
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc


@router.post("/upload")
def upload(file: UploadFile, uid: str | None = None):
    paper_uid = _store(file, uid)
    with closing(_connect()) as conn:
        return process_saved_pdf(conn, paper_uid)


@router.get("/{uid}/file")
def original(uid: str):
    if not _UID_RE.fullmatch(uid):
        raise HTTPException(400, "invalid uid")
    path = _data_dir() / f"{uid}.pdf"
    if not path.is_file():
        raise HTTPException(404, "本地原文不可用，请上传 PDF")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{uid}.pdf",
        content_disposition_type="inline",
    )


class Metadata(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    year: int | None = Field(default=None, ge=1500, le=2100)
    code_url: str | None = None


@router.patch("/{uid}")
def edit(uid: str, req: Metadata):
    if req.code_url and not req.code_url.startswith("https://"):
        raise HTTPException(422, "代码链接必须使用 HTTPS")
    with closing(_connect()) as conn:
        if not get_paper(conn, uid):
            raise HTTPException(404, "paper not found")
        conn.execute(
            "UPDATE papers SET title=?,year=?,code_url=? WHERE uid=?",
            (req.title, req.year, req.code_url, uid),
        )
        conn.commit()
        return get_paper(conn, uid)


@router.get("/{uid}")
def get_one(uid: str):
    with closing(_connect()) as conn:
        row = get_paper(conn, uid)
    if row is None:
        raise HTTPException(404, "paper not found")
    return row


@router.get("")
def list_papers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str = "",
    parse_status: str | None = None,
):
    where = "WHERE (title LIKE ? OR abstract LIKE ?)"
    args = [f"%{q}%", f"%{q}%"]
    if parse_status:
        where += " AND parse_status=?"
        args.append(parse_status)
    with closing(_connect()) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM papers {where}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT uid,title,year,source,parse_status FROM papers {where} ORDER BY created_at DESC,uid LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.post("/{uid}/fetch-fulltext", status_code=202)
def fetch_fulltext(uid: str):
    from app.jobs import enqueue

    with closing(_connect()) as conn:
        if not get_paper(conn, uid):
            raise HTTPException(404, "paper not found")
    try:
        return {"task_id": enqueue("download", {"uid": uid})}
    except RuntimeError as exc:
        raise HTTPException(429, str(exc)) from exc
