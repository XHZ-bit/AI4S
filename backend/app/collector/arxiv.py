import xml.etree.ElementTree as ET

import httpx

from app.models.paper import PaperDoc, normalize_arxiv_id

ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom"}
_HEADERS = {"User-Agent": "research-atlas/0.1 (academic research tool)"}


def _entry_to_doc(entry: ET.Element) -> PaperDoc | None:
    raw_id = entry.findtext("a:id", "", _NS).rsplit("/", 1)[-1]
    if not raw_id:
        return None
    title = " ".join(entry.findtext("a:title", "", _NS).split())
    abstract = " ".join(entry.findtext("a:summary", "", _NS).split())
    authors = [a.findtext("a:name", "", _NS) for a in entry.findall("a:author", _NS)]
    published = entry.findtext("a:published", "", _NS)
    year = int(published[:4]) if published else 0
    categories = [c.get("term") for c in entry.findall("a:category", _NS) if c.get("term")]
    pdf_url = None
    for link in entry.findall("a:link", _NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
    return PaperDoc(
        uid=normalize_arxiv_id(raw_id),
        arxiv_id=normalize_arxiv_id(raw_id),
        title=title,
        abstract=abstract,
        authors=authors,
        year=year,
        categories=categories,
        published=published or None,
        pdf_url=pdf_url,
    )


def _search_query(keywords: list[str], categories: list[str]) -> str:
    kw = " OR ".join(f'all:"{k}"' for k in keywords)
    cat = " OR ".join(f"cat:{c}" for c in categories)
    return f"({kw}) AND ({cat})"


def fetch_topic(
    client: httpx.Client,
    keywords: list[str],
    categories: list[str],
    start_year: int,
    max_results: int,
) -> list[PaperDoc]:
    resp = client.get(
        ARXIV_API,
        params={
            "search_query": _search_query(keywords, categories),
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    docs = []
    for entry in root.findall("a:entry", _NS):
        doc = _entry_to_doc(entry)
        if doc and doc.year >= start_year:
            docs.append(doc)
    return docs
