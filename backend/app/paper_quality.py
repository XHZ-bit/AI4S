"""Measured PDF text coverage, with no invented OCR or semantic quality score."""

import json
import pymupdf


def init_quality(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS paper_parse_quality (document_id TEXT PRIMARY KEY, "
                 "paper_uid TEXT NOT NULL, report_json TEXT NOT NULL)")


def record_quality(conn, uid, did, raw, parsed):
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        pages = len(pdf)
        text_pages = sum(bool(page.get_text().strip()) for page in pdf)
    report = {"document_id": did, "paper_uid": uid, "page_count": pages,
              "text_page_count": text_pages, "text_page_ratio": text_pages / pages if pages else 0,
              "section_count": len(parsed.sections), "character_count": sum(len(s.text) for s in parsed.sections),
              "status": "ready" if text_pages == pages and pages else "partial" if text_pages else "no_text",
              "warnings": [], "measurement": "PDF 页面文字层覆盖率；不代表公式、图表或语义解析正确率"}
    if text_pages < pages:
        report['warnings'].append("部分页面没有文字层，可能是扫描页；请在原文阅读器中查看。当前未执行 OCR。")
    if not parsed.sections:
        report['warnings'].append("没有可用正文片段；自动阅读清单不可生成。")
    conn.execute("INSERT OR REPLACE INTO paper_parse_quality VALUES(?,?,?)", (did, uid, json.dumps(report, ensure_ascii=False)))
    conn.commit()
    return report


def paper_quality(conn, uid):
    row = conn.execute("SELECT d.id,d.content_hash,d.coverage,q.report_json FROM documents d "
                       "LEFT JOIN paper_parse_quality q ON q.document_id=d.id WHERE d.paper_uid=? "
                       "ORDER BY d.created_at DESC,d.rowid DESC LIMIT 1", (uid,)).fetchone()
    if not row:
        return {"status": "pending", "warnings": ["原文尚未解析，可在处理进度中查看或重试"]}
    report = json.loads(row['report_json']) if row['report_json'] else {
        "status": "unknown", "warnings": ["旧资料没有页面覆盖率记录；已有正文仍可阅读"]}
    return {**report, "document_id": row['id'], "source_version": row['content_hash'],
            "document_versions": conn.execute("SELECT COUNT(*) FROM documents WHERE paper_uid=?", (uid,)).fetchone()[0]}
