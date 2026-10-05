"""
文件名: fallback.py
描述: PyMuPDF 本地 PDF 文本提取（GROBID 不可用时的降级路径）
"""

import pymupdf as fitz


def parse_with_pymupdf(pdf_bytes: bytes) -> dict:
    sections = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                sections.append({"heading": f"Page {i + 1}", "text": text, "page": i + 1})
    title = sections[0]["text"].splitlines()[0].strip() if sections else ""
    abstract = ""  # A page prefix is not necessarily an abstract.
    return {"title": title, "abstract": abstract, "sections": sections}
