from contextlib import closing
from fastapi import APIRouter, Query
from app.db.sqlite import connect
from app.search.service import semantic_search

router = APIRouter(prefix="/api/search", tags=["search"])


def _connect():
    return connect()


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
