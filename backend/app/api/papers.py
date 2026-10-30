"""Original files are saved before processing; failures can be retried."""

import hashlib
import re
from contextlib import closing
import pymupdf
from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
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
    from app.tenancy import data_dir

    path = data_dir() / "pdfs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def process_saved_pdf(conn, uid):
    path = _data_dir() / f"{uid}.pdf"
    stage(conn, uid, "parse", "running")
    try:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        prior = conn.execute("SELECT id FROM documents WHERE paper_uid=? AND content_hash=?", (uid, digest)).fetchone()
        if prior:
            if not conn.execute('SELECT 1 FROM paper_parse_quality WHERE document_id=?', (prior['id'],)).fetchone():
                from app.paper_quality import record_quality
                from app.task_control import check_active
                parsed_quality = parse_pdf(uid, raw, filename=path.name)
                check_active(conn)
                record_quality(conn, uid, prior['id'], raw, parsed_quality)
            stage(conn, uid, "parse", "done")
            _sync_optional(conn, uid, get_paper(conn, uid))
            return {"uid": uid, "parse_status": "parsed", "reused": True}
        parsed = parse_pdf(uid, raw, filename=path.name)
        from app.task_control import check_active
        check_active(conn)
        paper = get_paper(conn, uid)
        # The local fallback extracts page text, but cannot identify an abstract.
        # Keep collected metadata when a parser has no replacement for it.
        paper.update(
            title=parsed.title.strip() or paper["title"],
            abstract=parsed.abstract.strip() or paper["abstract"],
        )
        upsert_paper(conn, paper)
        did = save_document(conn, uid, parsed, digest, path.name)
        from app.paper_quality import record_quality
        quality = record_quality(conn, uid, did, raw, parsed)
        conn.execute("UPDATE papers SET parse_status='parsed' WHERE uid=?", (uid,))
        conn.commit()
        stage(conn, uid, "parse", "done")
    except Exception as exc:
        stage(conn, uid, "parse", "failed", str(exc))
        raise
    _sync_optional(conn, uid, paper)
    return {"uid": uid, "parse_status": "parsed", "quality": quality}


def _sync_optional(conn, uid, paper):
    from app.knowledge.unified import sync_metadata
    sync_metadata(conn, uid=uid)
    conn.commit()
    from app.task_control import check_active
    from app.config import get_settings
    if get_settings().access_mode == "multiuser":
        # Intentionally disabled providers are not parse failures or retry work.
        check_active(conn)
        stage(conn, uid, "graph", "skipped")
        stage(conn, uid, "index", "skipped")
        return
    for name, operation in [
        ("graph", lambda: merge_paper(paper)),
        (
            "index",
            lambda: index_paper(conn, uid, paper['title'] + "\n" + paper['abstract']),
        ),
    ]:
        check_active(conn)
        if name == "graph":
            from app.db.neo4j_client import graph_reachable
            if not graph_reachable():
                # SQLite is already the source of the local graph projection.
                stage(conn, uid, name, "done")
                continue
        done = conn.execute('SELECT status FROM pipeline_stages WHERE paper_uid=? AND stage=?', (uid,name)).fetchone()
        if done and done['status'] == 'done':
            continue
        stage(conn, uid, name, "running")
        try:
            operation()
            stage(conn, uid, name, "done")
        except Exception as exc:
            stage(conn, uid, name, "failed", str(exc))


def _store(file, uid=None):
    from app.tenancy import workspace_write_lock
    with workspace_write_lock():
        return _store_locked(file, uid)


def _store_locked(file, uid=None):
    from app.config import get_settings
    settings = get_settings()
    managed = settings.access_mode == "multiuser"
    byte_limit = settings.user_pdf_max_bytes if managed else _MAX_PDF_BYTES
    if uid and (not _UID_RE.fullmatch(uid) or uid in (".", "..")):
        raise HTTPException(400, "invalid uid")
    raw = file.file.read(byte_limit + 1)
    if len(raw) > byte_limit:
        raise HTTPException(413, f"PDF 超过 {byte_limit // (1024 * 1024)}MB 限制")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(400, "文件不是有效的 PDF")
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as document:
            if document.needs_pass:
                raise HTTPException(422, "PDF 已加密，请先移除打开密码后重新上传")
            if document.page_count == 0:
                raise HTTPException(422, "PDF 没有可读取的页面，请检查文件后重新上传")
            if managed and document.page_count > settings.user_pdf_max_pages:
                raise HTTPException(413, f"PDF 超过 {settings.user_pdf_max_pages} 页限制")
    except (pymupdf.FileDataError, ValueError) as exc:
        raise HTTPException(422, "PDF 已损坏或无法读取，请检查文件后重新上传") from exc
    digest = hashlib.sha256(raw).hexdigest()
    paper_uid = uid or f"upload-{digest[:24]}"
    path = _data_dir() / f"{paper_uid}.pdf"
    with closing(_connect()) as conn:
        if uid is None:
            existing = conn.execute('SELECT paper_uid FROM documents WHERE content_hash=? ORDER BY created_at,paper_uid LIMIT 1', (digest,)).fetchone()
            if existing and get_paper(conn, existing['paper_uid']):
                saved_file = _data_dir()/f"{existing['paper_uid']}.pdf"
                if saved_file.is_file() and saved_file.read_bytes() == raw:
                    return existing['paper_uid']
        from app.storage import save_original

        if managed and not path.exists():
            if not get_paper(conn, paper_uid) and conn.execute('SELECT COUNT(*) FROM papers').fetchone()[0] >= settings.user_max_papers:
                raise HTTPException(409, "个人论文数量已达到当前配额")
            used = sum(saved.stat().st_size for saved in _data_dir().iterdir() if saved.is_file())
            if used + len(raw) > settings.user_storage_max_bytes:
                raise HTTPException(413, "个人原文空间已达到当前配额")

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
            "task_id": enqueue("parse", {"uid": uid}),
            "parse_status": "queued",
        }
    except RuntimeError as exc:
        return JSONResponse(status_code=429, content={
            "detail": f"原文已保存，尚未排入解析；{exc}。请稍后重试解析，无需重新上传文件。",
            "saved": True, "uid": uid, "parse_status": "not_queued", "retryable": True,
        })


@router.post("/upload")
def upload(file: UploadFile, uid: str | None = None):
    paper_uid = _store(file, uid)
    with closing(_connect()) as conn:
        return process_saved_pdf(conn, paper_uid)


@router.get("/{uid}/quality")
def quality_report(uid: str):
    from app.paper_quality import paper_quality
    with closing(_connect()) as conn:
        if not get_paper(conn, uid):
            raise HTTPException(404, "论文不存在")
        return paper_quality(conn, uid)


@router.post('/{uid}/parse', status_code=202)
def reparse(uid: str):
    from app.jobs import enqueue
    if not _UID_RE.fullmatch(uid) or not (_data_dir()/f'{uid}.pdf').is_file():
        raise HTTPException(404, '本地原文不存在，请先上传 PDF')
    with closing(_connect()) as conn:
        if not get_paper(conn, uid):
            raise HTTPException(404, '论文不存在')
    try:
        return {'task_id': enqueue('parse', {'uid':uid})}
    except RuntimeError as exc:
        raise HTTPException(429,str(exc)) from exc


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
