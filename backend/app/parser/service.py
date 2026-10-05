"""
文件名: service.py
描述: PDF 解析编排入口，GROBID 优先、PyMuPDF 降级
"""

import logging
import xml.etree.ElementTree as ET

import httpx

from app.models.paper import ParsedPaper
from app.parser import fallback, grobid

logger = logging.getLogger(__name__)


def parse_pdf(
    uid: str, pdf_bytes: bytes, filename: str = "paper.pdf", grobid_base: str | None = None
) -> ParsedPaper:
    base = grobid_base
    if base is None:
        from app.config import get_settings

        base = get_settings().grobid_base_url
    try:
        with httpx.Client() as client:
            if grobid.is_alive(client, base):
                data = grobid.parse_with_grobid(client, base, pdf_bytes, filename)
                if data["title"]:
                    return ParsedPaper(uid=uid, **data)
    except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
        logger.warning("GROBID parse failed, falling back to PyMuPDF: %s", exc)
    data = fallback.parse_with_pymupdf(pdf_bytes)
    return ParsedPaper(uid=uid, **data)
