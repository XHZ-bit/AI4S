"""Explicit, bounded citation discovery with workspace-local metadata cache."""

import json
import time
from contextlib import closing
from urllib.parse import quote
import httpx
from fastapi import APIRouter, HTTPException, Query
from app import preferences
from app.config import get_settings
from app.db.sqlite import connect, get_paper
from app.api.stride import setup
from app.api.stride_learning import features
from app.graphsvc import queries

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/explore")
def explore(
    seed: str,
    direction: str = Query("references", pattern="^(references|citations)$"),
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(20, ge=1, le=50),
    project_id: str | None = None,
    remote: bool = False,
):
    if not preferences.enabled("graph"):
        raise HTTPException(409, "图谱已关闭")
    with closing(connect()) as c:
        setup(c)
        if not features(c, None if project_id == "library" else project_id).get(
            "graph"
        ):
            raise HTTPException(409, "此课题图谱已关闭")
        if project_id and project_id != "library":
            from app.db import projects

            if not any(
                x.paper_uid == seed and x.status.value == "active"
                for x in projects.list_paper_links(c, project_id)
            ):
                raise HTTPException(404, "种子论文未关联本课题")
        p = get_paper(c, seed)
        if not p:
            raise HTTPException(404, "请先把种子论文加入资料库")
        c.execute(
            "CREATE TABLE IF NOT EXISTS stride_reference_cache(key TEXT PRIMARY KEY,data TEXT NOT NULL,created REAL NOT NULL)"
        )
        key = json.dumps([seed, direction, offset, limit, project_id])
        row = c.execute(
            "SELECT data,created FROM stride_reference_cache WHERE key=?", (key,)
        ).fetchone()
        if remote and row and time.time() - row[1] < 86400:
            return {**json.loads(row[0]), "cached": True}
        arxiv = p.get("arxiv_id")
        title = p["title"]
    if project_id:
        from app.graphsvc.local import view

        local = view(uid=seed, depth=1, limit=50, project_id=project_id)
    else:
        local = queries.neighbors(seed, depth=1, limit=50)
    if not remote:
        return {
            "local": local,
            "items": [],
            "next": None,
            "notice": "当前显示已保存资料的一跳关系。",
            "cached": False,
        }
    if get_settings().offline_mode:
        return {
            "local": local,
            "items": [],
            "next": None,
            "notice": "离线模式：保留本地关系。",
            "cached": False,
        }
    if not arxiv:
        return {
            "local": local,
            "items": [],
            "next": None,
            "notice": "此种子没有 arXiv 标识，可继续探索本地关系。",
            "cached": False,
        }
    relation = "citedPaper" if direction == "references" else "citingPaper"
    url = (
        get_settings().s2_api_base.rstrip("/")
        + "/paper/"
        + quote("arXiv:" + arxiv, safe=":")
        + "/"
        + direction
    )
    try:
        with httpx.Client(
            timeout=20, trust_env=False, follow_redirects=False
        ) as client:
            response = client.get(
                url,
                params={
                    "fields": f"{relation}.title,{relation}.year,{relation}.externalIds,{relation}.url",
                    "offset": offset,
                    "limit": limit,
                },
                headers={"User-Agent": "PaperStride/0.1"},
            )
            response.raise_for_status()
            body = response.json()
        items = []
        for row in body.get("data", []):
            item = row.get(relation) or {}
            ids = item.get("externalIds") or {}
            items.append(
                {
                    "id": item.get("paperId"),
                    "title": item.get("title") or "未提供题名",
                    "year": item.get("year"),
                    "identifier": ids.get("ArXiv") or ids.get("DOI"),
                    "url": item.get("url"),
                    "origin": "citation_metadata",
                    "reason": f"被「{title}」引用"
                    if direction == "references"
                    else f"引用了「{title}」",
                    "direction": direction,
                }
            )
        result = {
            "local": local,
            "items": items,
            "next": body.get("next"),
            "notice": "引用关系来自 Semantic Scholar，不代表结论已核验。",
            "cached": False,
        }
        with closing(connect()) as c:
            c.execute(
                "INSERT OR REPLACE INTO stride_reference_cache VALUES(?,?,?)",
                (key, json.dumps(result, ensure_ascii=False), time.time()),
            )
            c.commit()
        return result
    except (httpx.HTTPError, ValueError, KeyError):
        return {
            "local": local,
            "items": [],
            "next": None,
            "notice": "文献服务暂时不可用或限流；本地资料仍可探索，请稍后重试。",
            "cached": False,
        }
