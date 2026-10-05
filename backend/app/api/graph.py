from fastapi import APIRouter, Query

from app.graphsvc import queries

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/nodes")
def nodes(
    q: str = "",
    entity_type: str | None = Query(None, alias="type"),
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    return {"items": queries.search_nodes(q, node_type=entity_type, limit=limit)}


@router.get("/overview")
def overview(limit: int = Query(100, ge=1, le=500)) -> dict:
    return queries.overview(limit=limit)


@router.get("/neighbors/{uid}")
def nbrs(
    uid: str,
    depth: int = Query(1, ge=1, le=3),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    return queries.neighbors(uid, depth=depth, limit=limit)
