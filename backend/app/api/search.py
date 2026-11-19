from contextlib import closing
from typing import Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.db.sqlite import connect
from app.search.service import index_papers, lexical_search, semantic_search
from app.tenancy import workspace_write_lock

router = APIRouter(prefix="/api/search", tags=["search"])


def _connect():
    return connect()


@router.post("/reindex")
def reindex():
    """Explicitly build embeddings for the current account's paper library."""
    with workspace_write_lock(), closing(_connect()) as conn:
        papers = conn.execute("SELECT uid,title,abstract FROM papers ORDER BY uid").fetchall()
        try:
            index_papers(conn, [(row["uid"], f"{row['title'] or ''}\n{row['abstract'] or ''}") for row in papers])
        except Exception:
            raise HTTPException(502, "索引未全部完成，请检查向量模型配置或服务后重试。已完成的批次保留。") from None
        return {"indexed": len(papers)}


class SearchHit(BaseModel):
    uid: str
    title: str
    snippet: str
    score: float
    hit_reason: str
    year: int | None = None
    source: str | None = None
    # These are present only for a matching stored passage. quote is an exact
    # substring of passage.text; page is one-based when supplied by the parser.
    passage_id: str | None = None
    document_id: str | None = None
    document_version: str | None = None
    page: int | None = None
    quote: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchHit]
    mode: Literal["keyword", "semantic", "hybrid"]
    notice: str


@router.get("/v2", response_model=SearchResponse, response_model_exclude_unset=True)
def search_v2(q: str, limit: int = Query(10, ge=1, le=50)):
    if not q.strip():
        return {"items": [], "mode": "keyword", "notice": "请输入检索词"}
    with closing(_connect()) as conn:
        lexical = lexical_search(conn, q, limit=50)
        semantic = []
        semantic_notice = ""
        if conn.execute("SELECT 1 FROM paper_embeddings LIMIT 1").fetchone():
            try:
                semantic = semantic_search(conn, q, limit=50)
            except Exception:
                semantic_notice = "当前向量模型不可用或索引需要重建，已使用关键词检索。"
        merged = {}
        for rank, item in enumerate(lexical, 1):
            merged[item["uid"]] = {**item, "score": 2 / (60 + rank)}
        used_semantic = False
        for rank, item in enumerate(semantic, 1):
            entry = merged.get(item["uid"])
            if entry is None:
                row = conn.execute("SELECT title,abstract,year,source FROM papers WHERE uid=?", (item["uid"],)).fetchone()
                if row is None:
                    continue
                entry = dict(uid=item["uid"], title=row["title"],
                             snippet=(row["abstract"] or "")[:280], year=row["year"],
                             source=row["source"], hit_reason="语义相近", score=0)
                merged[item["uid"]] = entry
            else:
                entry["hit_reason"] += " + 语义相近"
            entry["score"] += 1 / (60 + rank)
            used_semantic = True
        items = sorted(merged.values(), key=lambda item: (-item["score"], item["uid"]))[:limit]
        return {"items": items, "mode": "hybrid" if used_semantic and lexical else "semantic" if used_semantic else "keyword",
                "notice": semantic_notice or "排名仅表示检索相关性，不表示论文质量或结论可靠性。"}


@router.get("")
def search(q: str, limit: int = Query(10, ge=1, le=50)):
    if not q.strip():
        return {"items": [], "mode": "keyword"}
    with closing(_connect()) as conn:
        mode = "semantic"
        try:
            items = semantic_search(conn, q, limit=limit)
        except Exception:
            mode = "keyword"
            rows = conn.execute(
                "SELECT uid FROM papers WHERE title LIKE ? OR abstract LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{q}%", f"%{q}%", limit),
            ).fetchall()
            items = [{"uid": r["uid"], "score": None} for r in rows]
        for item in items:
            row = conn.execute(
                "SELECT title,abstract,year,source FROM papers WHERE uid=?",
                (item["uid"],),
            ).fetchone()
            if row:
                item.update(
                    title=row["title"],
                    snippet=row["abstract"][:350],
                    year=row["year"],
                    source=row["source"],
                )
        return {"items": items, "mode": mode}
