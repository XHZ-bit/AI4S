"""Unified sources, graph, learning and comparisons in an isolated research space."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.knowledge import comparison, learning, model, service, sources, store

router = APIRouter(prefix="/api/projects/{project_id}", tags=["knowledge-workspace"])


class Link(BaseModel):
    url: str = Field(min_length=1, max_length=3000)
    kind: Literal["paper", "code", "report", "results"] | None = None


class Attach(BaseModel):
    paper_uid: str = Field(min_length=1, max_length=150)


class Analyze(BaseModel):
    source_id: str
    retry: bool = False


class SourcePatch(BaseModel):
    removed: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)


class Preferences(BaseModel):
    mode: Literal["explore", "research", "reproduce"] | None = None
    view: Literal["graph", "reading", "learning", "compare", "materials", "practice"] | None = None


class NodePatch(BaseModel):
    expected_version: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=250)
    summary: str | None = Field(default=None, max_length=30000)
    hidden: bool | None = None
    latex: str | None = Field(default=None, max_length=10000)
    research_status: Literal["unspecified", "proposed", "implemented", "reported_result", "pending_validation"] | None = None


class EdgePatch(BaseModel):
    expected_version: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=150)
    explanation: str | None = Field(default=None, max_length=10000)
    hidden: bool | None = None


class Merge(BaseModel):
    node_ids: list[str] = Field(min_length=2, max_length=20)
    label: str | None = Field(default=None, min_length=1, max_length=250)


class Generate(BaseModel):
    refresh: bool = False


class LearningGenerate(Generate):
    goal: str = Field(default="", max_length=1500)
    depth: Literal["standard", "deep"] = "deep"


LearningSection = Literal['overview', 'definition', 'derivation', 'prerequisites', 'implementation', 'limitations']


class LearningPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    sections: dict[LearningSection, Annotated[str, Field(max_length=25000)]] | None = None
    hidden_sections: list[LearningSection] | None = Field(default=None, max_length=6)
    goal: str | None = Field(default=None, max_length=1500)
    depth: Literal["standard", "deep"] | None = None


class Compare(Generate):
    source_ids: list[str] = Field(min_length=2, max_length=8)
    focus_node_ids: list[str] = Field(default_factory=list, max_length=8)
    dimensions: list[str] | None = Field(default=None, max_length=12)


class ComparisonPatch(Compare):
    expected_revision: int = Field(ge=1)
    dimension: str = Field(min_length=1, max_length=100)
    source_id: str
    text: str = Field(max_length=12000)


@router.get("/sources")
def list_sources(project_id: str, include_removed: bool = False):
    with store.connection(project_id) as conn:
        return {"items": store.sources(conn, project_id, include_removed=include_removed), "preferences": store.preferences(conn, project_id),
                "model": {"configured": model.configured(), "enabled": model.available()}}


def _submitted(project_id, source):
    analysis = service.enqueue(project_id, source["id"])
    with store.connection(project_id) as conn:
        return {"source": store.source(conn, project_id, source["id"]), "analysis": analysis}


@router.post("/sources", status_code=202)
def upload_source(project_id: str, file: UploadFile = File(...), kind: str | None = Form(default=None)):
    return _submitted(project_id, sources.ingest(project_id, file.file.read(sources.MAX_BYTES + 1), file.filename or "source.txt", kind))


@router.post("/sources/link", status_code=202)
def link_source(project_id: str, req: Link):
    return _submitted(project_id, sources.ingest_link(project_id, req.url, req.kind))


@router.post("/sources/attach", status_code=202)
def attach_source(project_id: str, req: Attach):
    return _submitted(project_id, sources.attach(project_id, req.paper_uid))


@router.get("/sources/{source_id}")
def get_source(project_id: str, source_id: str):
    with store.connection(project_id) as conn:
        value = store.source(conn, project_id, source_id, blocks=True, include_removed=True)
        evidence_blocks = {r[0]: json.loads(r[1])["block_id"] for r in conn.execute("SELECT id,data FROM kw_evidence WHERE project_id=? AND source_id=?", (project_id, source_id))}
        linked = []
        for row in conn.execute("SELECT data FROM kw_nodes WHERE project_id=? AND source_id=? AND hidden=0", (project_id, source_id)):
            n = json.loads(row[0])
            if not n.get("parent_id"):
                continue
            bids = [evidence_blocks[e] for e in n["evidence_ids"] if e in evidence_blocks]
            if n.get("metadata", {}).get("block_id"):
                bids.append(n["metadata"]["block_id"])
            linked.append({"id": n["id"], "label": n["label"], "kind": n["kind"], "block_ids": list(dict.fromkeys(bids))})
        value["knowledge_nodes"] = linked
        return value


@router.patch("/sources/{source_id}")
def patch_source(project_id: str, source_id: str, req: SourcePatch):
    with store.connection(project_id) as conn:
        changes = req.model_dump(exclude_none=True)
        if "title" in changes:
            changes["title_user_edited"] = True
        value = store.update_source(conn, project_id, source_id, changes)
        if value["removed"]:
            rows = conn.execute("SELECT id FROM kw_runs WHERE project_id=? AND source_id=? AND status IN ('queued','running')", (project_id, source_id)).fetchall()
            for row in rows:
                store.update_run(conn, project_id, row[0], status="cancelled")
        return value


@router.get("/sources/{source_id}/file")
def source_file(project_id: str, source_id: str):
    with store.connection(project_id) as conn:
        src = store.source(conn, project_id, source_id, include_removed=True)
        row = conn.execute("SELECT path FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()
    path = Path(row[0])
    if not path.is_file():
        raise HTTPException(404, "原始资料文件缺失")
    media = src["media_type"]
    active = path.suffix.lower() in {".html", ".htm", ".svg", ".js", ".mjs"}
    return FileResponse(path, media_type="text/plain" if active else media, filename=src["filename"],
                        content_disposition_type="attachment" if active else "inline",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.get("/sources/{source_id}/images/{block_id}")
def source_image(project_id: str, source_id: str, block_id: str):
    with store.connection(project_id) as conn:
        src = store.source(conn, project_id, source_id, blocks=True, include_removed=True)
        block = next((b for b in src["blocks"] if b["id"] == block_id), None)
        asset = conn.execute("SELECT path FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()
    if block is None:
        raise HTTPException(404, "图像不属于当前资料")
    meta = block.get("metadata", {})
    if meta.get("image_base64"):
        import base64
        image = base64.b64decode(meta["image_base64"])
        mime = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg" if image.startswith(b"\xff\xd8\xff") else "image/gif" if image.startswith(b"GIF8") else "image/webp" if image.startswith(b"RIFF") and image[8:12] == b"WEBP" else None
        if not mime:
            raise HTTPException(415, "该嵌入图像格式不能直接预览，请查看原文件")
        return Response(image, media_type=mime, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'"})
    if Path(asset[0]).suffix.lower() == ".pdf" and block.get("page") and block.get("bbox"):
        import pymupdf
        with pymupdf.open(asset[0]) as pdf:
            page = pdf[block["page"] - 1]
            box = pymupdf.Rect(block["bbox"])
            # Formula layout boxes can touch superscripts and radicals. Preserve
            # a small source margin instead of cutting those glyphs at the edge.
            if block.get("kind") == "formula":
                box = pymupdf.Rect(box.x0 - 4, box.y0 - 3, box.x1 + 4, box.y1 + 4)
            clip = box & page.rect
            scale = 2 if block.get("kind") == "formula" else 1.5
            return Response(page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip).tobytes("png"), media_type="image/png")
    raise HTTPException(404, "该内容块没有可读取的原图")


@router.post("/analysis", status_code=202)
def analyze_source(project_id: str, req: Analyze):
    return service.enqueue(project_id, req.source_id, retry=req.retry)


@router.get("/analysis")
def list_analysis(project_id: str):
    with store.connection(project_id) as conn:
        return {"items": [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_runs WHERE project_id=? ORDER BY rowid DESC LIMIT 100", (project_id,))]}


@router.post("/analysis/{run_id}/cancel")
def cancel_analysis(project_id: str, run_id: str):
    with store.connection(project_id) as conn:
        current = store.run(conn, project_id, run_id)
        if current["status"] not in {"queued", "running"}:
            return current
        return store.update_run(conn, project_id, run_id, status="cancelled")


@router.get("/knowledge/preferences")
def get_preferences(project_id: str):
    with store.connection(project_id) as conn:
        return store.preferences(conn, project_id)


@router.patch("/knowledge/preferences")
def patch_preferences(project_id: str, req: Preferences):
    with store.connection(project_id) as conn:
        return store.save_preferences(conn, project_id, req.model_dump(exclude_none=True))


@router.get("/knowledge/graph")
def knowledge_graph(project_id: str, source_id: str | None = None, node_id: str | None = None, q: str | None = Query(None, max_length=300),
                    kind: str | None = None, limit: int = Query(100, ge=1, le=2000), include_hidden: bool = False, overview: bool = False):
    with store.connection(project_id) as conn:
        graph = store.graph(conn, project_id, source_id=source_id, node_id=node_id, q=q, kind=kind, limit=limit, include_hidden=include_hidden, overview=overview)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kw_progress'").fetchone():
            progress = {r[0]: json.loads(r[1]) for r in conn.execute("SELECT node_id,data FROM kw_progress WHERE project_id=?", (project_id,))}
            for node in graph['nodes']:
                if node['id'] in progress:
                    entry = progress[node['id']]
                    node['metadata'] = {**node.get('metadata', {}), 'learning_progress': entry['status'],
                                        'learning_progress_stale': entry.get('node_version') != node['version']}
        return graph


@router.post("/knowledge/nodes/merge")
def merge_nodes(project_id: str, req: Merge):
    with store.connection(project_id) as conn:
        return store.merge_nodes(conn, project_id, req.node_ids, req.label)


@router.post("/knowledge/nodes/{node_id}/split")
def split_node(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return store.split_node(conn, project_id, node_id)


@router.get("/knowledge/nodes/{node_id}")
def node_detail(project_id: str, node_id: str):
    with store.connection(project_id) as conn:
        return learning.detail(conn, project_id, node_id)


@router.patch("/knowledge/nodes/{node_id}")
def patch_node(project_id: str, node_id: str, req: NodePatch):
    with store.connection(project_id) as conn:
        changes = req.model_dump(exclude_none=True, exclude={"expected_version", "latex"})
        if req.latex is not None:
            node = store.record(conn, 'kw_nodes', project_id, node_id)
            if node['kind'] != 'formula':
                raise HTTPException(422, '只有公式节点可以修订 LaTeX')
            changes['metadata'] = {**node['metadata'], 'latex': req.latex, 'recognition': 'user_corrected'}
            changes['origin'] = 'user'
        return store.edit_record(conn, "kw_nodes", project_id, node_id, req.expected_version, changes)


@router.patch("/knowledge/edges/{edge_id}")
def patch_edge(project_id: str, edge_id: str, req: EdgePatch):
    with store.connection(project_id) as conn:
        return store.edit_record(conn, "kw_edges", project_id, edge_id, req.expected_version, req.model_dump(exclude_none=True, exclude={"expected_version"}))


@router.get("/knowledge/nodes/{node_id}/learning")
def get_learning(project_id: str, node_id: str, goal: str | None = Query(None, max_length=1500), depth: Literal["standard", "deep"] | None = None):
    with store.connection(project_id) as conn:
        return learning.get_learning(conn, project_id, node_id, goal, depth)


@router.post("/knowledge/nodes/{node_id}/learning")
def generate_learning(project_id: str, node_id: str, req: LearningGenerate = LearningGenerate()):
    return learning.generate(project_id, node_id, **req.model_dump())


@router.patch('/knowledge/nodes/{node_id}/learning')
def revise_learning(project_id: str, node_id: str, req: LearningPatch):
    return learning.revise(project_id, node_id, req.expected_revision, req.sections, req.hidden_sections, req.goal, req.depth)


@router.get("/knowledge/comparisons")
def get_comparisons(project_id: str):
    with store.connection(project_id) as conn:
        return {"items": comparison.list_comparisons(conn, project_id)}


@router.get('/knowledge/comparisons/preview')
def preview_comparison(project_id: str, source_ids: list[str] = Query(default=[]), focus_node_ids: list[str] = Query(default=[]), dimensions: list[str] | None = Query(default=None)):
    if not source_ids:
        with store.connection(project_id) as conn:
            source_ids = [s['id'] for s in store.sources(conn, project_id) if s['kind'] in {'paper', 'report'}][:8]
    if len(source_ids) < 2:
        return {'status': 'empty', 'source_ids': source_ids, 'rows': [], 'evidence': [], 'errors': [], 'auto_filled': True}
    return comparison.compare(project_id, source_ids, focus_node_ids=focus_node_ids, dimensions=dimensions, basic_only=True)


@router.post("/knowledge/comparisons")
def create_comparison(project_id: str, req: Compare):
    return comparison.compare(project_id, req.source_ids, req.refresh, req.focus_node_ids, req.dimensions)


@router.patch('/knowledge/comparisons/{comparison_id}')
def edit_comparison(project_id: str, comparison_id: str, req: ComparisonPatch):
    return comparison.revise(project_id, comparison_id, req.expected_revision, req.dimension, req.source_id, req.text, req.source_ids, req.focus_node_ids, req.dimensions)
