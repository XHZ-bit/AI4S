from fastapi import APIRouter, Query, Depends, HTTPException
from app import preferences
from app.graphsvc import queries
from app.graphsvc.resources import enrich


def enabled_graph():
    if not preferences.enabled("graph"):
        raise HTTPException(409, "图谱功能已关闭")


router = APIRouter(
    prefix="/api/graph", tags=["graph"], dependencies=[Depends(enabled_graph)]
)


@router.get("/nodes")
def nodes(
    q: str = "",
    entity_type: str | None = Query(None, alias="type"),
    limit: int = Query(20, ge=1, le=200),
    project_id: str | None = None,
) -> dict:
    if project_id:
        from app.graphsvc import local

        return {
            "items": local.search(
                q, node_type=entity_type, limit=limit, project_id=project_id
            )
        }
    return {
        "items": enrich(
            {"nodes": queries.search_nodes(q, node_type=entity_type, limit=limit)}
        )["nodes"]
    }


@router.get("/context")
def contextual_graph(
    q: str = "",
    entity_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=50),
    project_id: str | None = None,
    seed: str | None = None,
):
    from app.graphsvc import local

    return local.context(
        q, node_type=entity_type, limit=limit, project_id=project_id, seed=seed
    )


@router.get("/overview")
def overview(
    limit: int = Query(100, ge=1, le=500), project_id: str | None = None
) -> dict:
    if project_id:
        from app.graphsvc.local import view

        return enrich(view(limit=limit, project_id=project_id))
    return enrich(queries.overview(limit=limit))


@router.get("/neighbors/{uid}")
def nbrs(
    uid: str,
    depth: int = Query(1, ge=1, le=3),
    limit: int = Query(100, ge=1, le=500),
    project_id: str | None = None,
) -> dict:
    if project_id:
        from app.graphsvc import local

        return local.view(
            uid=uid, depth=depth, limit=min(limit, 50), project_id=project_id
        )
    return enrich(queries.neighbors(uid, depth=depth, limit=limit))
