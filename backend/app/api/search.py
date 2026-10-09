from contextlib import closing
from fastapi import APIRouter, Query
from app.db.sqlite import connect
from app.search.service import lexical_search, semantic_search

router = APIRouter(prefix="/api/search", tags=["search"])


def _connect():
    return connect()


@router.get("/v2")
def search_v2(q: str, limit: int = Query(10, ge=1, le=50)):
    if not q.strip():
        return {"items": [], "mode": "keyword", "notice": "请输入检索词"}
    with closing(_connect()) as conn:
        lexical = lexical_search(conn, q, limit=50)
        semantic = []
        if conn.execute("SELECT 1 FROM paper_embeddings LIMIT 1").fetchone():
            try:
                semantic = semantic_search(conn, q, limit=50)
            except Exception:
                pass  # Local lexical results remain available without a model.
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
                "notice": "排名仅表示检索相关性，不表示论文质量或结论可靠性。"}


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
