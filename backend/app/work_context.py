"""Bounded, account-local source selections shared by reading and tutoring."""

import json
import re
from urllib.parse import unquote, urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator


def safe_return_path(value: str | None) -> str | None:
    """A return destination is a route in this app, never a redirect target."""
    if value is None:
        return None
    parsed = urlsplit(value)
    path = unquote(parsed.path)
    if (not value.startswith('/') or path.startswith('//') or parsed.scheme
            or parsed.netloc or '\\' in path or re.search(r'[\x00-\x20\x7f]', value)
            or re.search(r'[\x00-\x20\x7f]', path)):
        raise ValueError('返回位置必须是站内页面')
    if not re.match(r'^/(?:research|papers|learn|practice|cases|explore|manage|workflow|tasks|actions|roadmap)(?:/|$)', path) and path != '/':
        raise ValueError('返回位置不是可恢复的工作页面')
    return value


class SourceSelection(BaseModel):
    document_id: str = Field(min_length=1, max_length=150)
    document_version: str | None = Field(default=None, max_length=150)
    page: int = Field(ge=1, le=10000)
    quote: str = Field(min_length=1, max_length=8000)

    @field_validator('quote')
    @classmethod
    def nonblank_quote(cls, value):
        if not value.strip():
            raise ValueError('请先选择一段文字')
        return value


def validate_document(conn, paper_uid, document_id, document_version=None, page=None):
    if not paper_uid:
        raise HTTPException(422, '选文必须关联当前论文')
    doc = conn.execute(
        'SELECT id,paper_uid,content_hash FROM documents WHERE id=? AND paper_uid=?',
        (document_id, paper_uid),
    ).fetchone()
    if doc is None:
        raise HTTPException(404, '选文文档不属于当前论文或当前空间')
    if document_version and document_version.removeprefix('sha256:') != doc['content_hash']:
        raise HTTPException(409, '选文文档版本已变化，请重新选择原文')
    if page:
        quality = conn.execute(
            'SELECT report_json FROM paper_parse_quality WHERE document_id=? AND paper_uid=?',
            (document_id, paper_uid),
        ).fetchone()
        if quality:
            try:
                report = json.loads(quality[0])
                count = report.get('page_count') if isinstance(report, dict) else None
                if type(count) is int and count > 0 and page > count:
                    raise HTTPException(422, f'选文页码不能超过文档的 {count} 页')
            except (ValueError, TypeError):
                pass
    return doc


def _normalized_text(text):
    # PDF text selections often join wrapped lines. This is textual matching,
    # not a claim that the text entails a model's later explanation.
    return re.sub(r'\s+', ' ', re.sub(r'(?<=\w)-\s*\n\s*(?=\w)', '', text)).strip()


def resolve_selection(conn, paper_uid, selection: SourceSelection):
    doc = validate_document(conn, paper_uid, selection.document_id,
                            selection.document_version, selection.page)
    rows = conn.execute(
        'SELECT id,text,heading,page,document_id FROM passages '
        'WHERE document_id=? AND page=? ORDER BY ordinal',
        (selection.document_id, selection.page),
    ).fetchall()
    needle = _normalized_text(selection.quote)
    matched = next((row for row in rows if selection.quote in row['text']), None)
    if matched is None:
        matched = next((row for row in rows if needle and needle in _normalized_text(row['text'])), None)
    result = {
        'document_id': doc['id'],
        'document_version': f"sha256:{doc['content_hash']}",
        'selection': {**selection.model_dump(), 'document_version': f"sha256:{doc['content_hash']}"},
        'selection_status': 'matched_passage' if matched else 'user_selection',
    }
    if matched:
        result['passage_id'] = matched['id']
        result['passage'] = {'text': matched['text'][:8000], 'heading': matched['heading'], 'page': matched['page']}
    return result
