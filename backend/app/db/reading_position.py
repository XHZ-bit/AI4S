"""Resume positions for exact document versions, separate from learning state."""

import json
import re
from datetime import datetime, timezone

import pymupdf


def init_reading_positions(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS paper_reading_positions (
      paper_uid TEXT NOT NULL REFERENCES papers(uid) ON DELETE CASCADE,
      document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      content_hash TEXT NOT NULL,
      page INTEGER NOT NULL CHECK(page>=1),
      page_count INTEGER NOT NULL CHECK(page_count>=page),
      updated_at TEXT NOT NULL,
      PRIMARY KEY(paper_uid,document_id));
    """)


class PositionError(ValueError):
    """A version or its real page bounds cannot be verified."""

    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def _document(conn, uid, document_id):
    doc = conn.execute(
        "SELECT d.id,d.paper_uid,d.content_hash FROM documents d JOIN papers p ON p.uid=d.paper_uid "
        "WHERE d.id=? AND d.paper_uid=?", (document_id, uid),
    ).fetchone()
    if doc is None:
        raise LookupError("论文或文档版本不存在")
    return doc


def _view(row):
    return {"paper_uid": row["paper_uid"], "document_id": row["document_id"],
            "document_version": f"sha256:{row['content_hash']}", "page": row["page"],
            "page_count": row["page_count"], "updated_at": row["updated_at"]}


def get_position(conn, uid, document_id):
    doc = _document(conn, uid, document_id)
    row = conn.execute(
        "SELECT * FROM paper_reading_positions WHERE paper_uid=? AND document_id=?", (uid, document_id),
    ).fetchone()
    if row is None:
        return None
    if row["content_hash"] != doc["content_hash"]:
        raise PositionError("文档版本已变化，无法使用原阅读位置")
    return _view(row)


def _page_count(conn, doc):
    quality = conn.execute(
        "SELECT report_json FROM paper_parse_quality WHERE document_id=? AND paper_uid=?",
        (doc["id"], doc["paper_uid"]),
    ).fetchone()
    if quality:
        try:
            report = json.loads(quality["report_json"])
            count = report.get("page_count") if isinstance(report, dict) else None
            if type(count) is int and count >= 1:
                return count
        except (ValueError, TypeError):
            pass
    # Legacy documents may lack a quality report. Only inspect the PDF whose
    # bytes match this exact version; never use the latest unrelated PDF's size.
    uid = doc["paper_uid"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", uid):
        raise PositionError("此文档版本没有可验证的页面数量")
    from app.knowledge.source_files import DocumentFileError, read_document_file
    try:
        _, raw = read_document_file(conn, uid, doc["id"])
    except DocumentFileError as exc:
        raise PositionError("此文档版本没有可核对的原始 PDF，暂不能保存阅读位置") from exc
    try:
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.page_count < 1:
                raise PositionError("此文档版本没有可验证的页面数量")
            return pdf.page_count
    except (pymupdf.FileDataError, ValueError) as exc:
        if isinstance(exc, PositionError):
            raise
        raise PositionError("无法读取此文档版本的页面数量") from exc


def save_position(conn, uid, document_id, page):
    if type(page) is not int or page < 1:
        raise PositionError("阅读页码必须为正整数", 422)
    conn.execute("BEGIN IMMEDIATE")
    try:
        doc = _document(conn, uid, document_id)
        count = _page_count(conn, doc)
        if page > count:
            raise PositionError(f"阅读页码不能超过此文档的 {count} 页", 422)
        current = get_position(conn, uid, document_id)
        if current is None or current["page"] != page or current["page_count"] != count:
            conn.execute(
                "INSERT INTO paper_reading_positions(paper_uid,document_id,content_hash,page,page_count,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(paper_uid,document_id) DO UPDATE SET "
                "content_hash=excluded.content_hash,page=excluded.page,page_count=excluded.page_count,"
                "updated_at=excluded.updated_at",
                (uid, document_id, doc["content_hash"], page, count,
                 datetime.now(timezone.utc).isoformat(timespec="microseconds")),
            )
        result = get_position(conn, uid, document_id)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
