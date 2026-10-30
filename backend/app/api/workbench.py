"""Account-scoped research notebook, synchronization, import and export services."""

import json
import re
import hashlib
import xml.etree.ElementTree as ET
from contextlib import closing
from typing import Literal
from urllib.parse import urlsplit, unquote, quote
from uuid import uuid4
import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from app.db.sqlite import connect, get_paper, upsert_paper
from app.db import projects
from app.models.research import PaperLinkCreate
from app.models.paper import PaperDoc
from app.tutoring import store as tutor_store
from app import preferences
from app.work_context import validate_document

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


def initialize(conn):
    projects.init_research_schema(conn)
    tutor_store(conn)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS workspace_records (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
      project_id TEXT, paper_uid TEXT, source_json TEXT, version INTEGER NOT NULL,
      updated_at TEXT DEFAULT (datetime('now')));
    CREATE INDEX IF NOT EXISTS workspace_records_project ON workspace_records(project_id,updated_at);
    CREATE TABLE IF NOT EXISTS project_tutor_sessions(project_id TEXT NOT NULL, session_id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS project_learning_preferences(project_id TEXT PRIMARY KEY, features_json TEXT NOT NULL);
    """)


def project_or_404(conn, identity):
    p = projects.get_project(conn, identity)
    if not p:
        raise HTTPException(404, "课题不在当前空间")
    return p


class Record(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=240)
    kind: Literal["note", "question", "experiment", "draft", "report"] = "note"
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=100000)
    project_id: str | None = Field(default=None, max_length=100)
    paper_uid: str | None = Field(default=None, max_length=150)
    page: int | None = Field(default=None, ge=1, le=10000)
    quote: str = Field(default="", max_length=8000)
    document_id: str | None = Field(default=None, max_length=150)
    document_version: str | None = Field(default=None, max_length=150)
    passage_id: str | None = Field(default=None, max_length=150)
    version: int = Field(default=0, ge=0)


@router.get("/records")
def records(project_id: str | None = None, paper_uid: str | None = None):
    with closing(connect()) as conn:
        initialize(conn)
        if project_id:
            project_or_404(conn, project_id)
        rows = conn.execute(
            "SELECT * FROM workspace_records WHERE (? IS NULL OR project_id=?) AND (? IS NULL OR paper_uid=?) ORDER BY updated_at DESC,id LIMIT 500",
            (project_id, project_id, paper_uid, paper_uid),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/records/{identity}")
def record(identity: str):
    with closing(connect()) as conn:
        initialize(conn)
        row = conn.execute(
            "SELECT * FROM workspace_records WHERE id=?", (identity,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "记录不存在")
        return dict(row)


@router.post("/records")
def save_record(req: Record):
    with closing(connect()) as conn:
        initialize(conn)
        if req.project_id:
            project_or_404(conn, req.project_id)
        if req.paper_uid and not get_paper(conn, req.paper_uid):
            raise HTTPException(404, "论文不在当前空间")
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute(
            "SELECT * FROM workspace_records WHERE id=?", (req.id,)
        ).fetchone()
        if (previous["version"] if previous else 0) != req.version:
            raise HTTPException(
                409,
                {
                    "message": "另一设备已修改，请比较后选择保留的内容",
                    "current": dict(previous) if previous else None,
                },
            )
        supplied = req.model_fields_set
        # Editing a title/body from an older client must not erase provenance.
        project_id = (
            req.project_id
            if "project_id" in supplied or not previous
            else previous["project_id"]
        )
        paper_uid = (
            req.paper_uid
            if "paper_uid" in supplied or not previous
            else previous["paper_uid"]
        )
        if project_id:
            project_or_404(conn, project_id)
        if paper_uid and not get_paper(conn, paper_uid):
            raise HTTPException(404, "论文不在当前空间")
        previous_source = (
            json.loads(previous["source_json"] or "{}") if previous else {}
        )
        fields = ("page", "quote", "document_id", "document_version", "passage_id")
        source_data = (
            previous_source if previous and previous["paper_uid"] == paper_uid else {}
        )
        source_data = {**source_data, "paper_uid": paper_uid}
        for key in fields:
            if key in supplied:
                source_data[key] = getattr(req, key)
        if source_data.get("passage_id"):
            passage = conn.execute(
                "SELECT p.document_id,p.page,d.content_hash FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=? AND d.paper_uid=?",
                (source_data["passage_id"], paper_uid),
            ).fetchone()
            if not passage:
                raise HTTPException(404, "原文片段不属于当前论文或当前空间")
            if (
                source_data.get("document_id")
                and source_data["document_id"] != passage["document_id"]
            ):
                raise HTTPException(422, "原文片段与文档不一致")
            if (
                source_data.get("page")
                and passage["page"]
                and source_data["page"] != passage["page"]
            ):
                raise HTTPException(422, "原文片段与页码不一致")
            source_data["document_id"] = passage["document_id"]
            source_data["page"] = source_data.get("page") or passage["page"]
        if source_data.get("document_id"):
            doc = validate_document(
                conn,
                paper_uid,
                source_data["document_id"],
                source_data.get("document_version"),
                source_data.get("page"),
            )
            source_data["document_version"] = "sha256:" + doc["content_hash"]
        elif source_data.get("document_version"):
            raise HTTPException(422, "文档版本必须关联文档")
        source = json.dumps(source_data, ensure_ascii=False)
        conn.execute(
            "INSERT INTO workspace_records(id,kind,title,body,project_id,paper_uid,source_json,version) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,title=excluded.title,body=excluded.body,project_id=excluded.project_id,paper_uid=excluded.paper_uid,source_json=excluded.source_json,version=excluded.version,updated_at=datetime('now')",
            (
                req.id,
                req.kind,
                req.title,
                req.body,
                project_id,
                paper_uid,
                source,
                req.version + 1,
            ),
        )
        conn.commit()
        return dict(
            conn.execute(
                "SELECT * FROM workspace_records WHERE id=?", (req.id,)
            ).fetchone()
        )


class ProjectFeatures(BaseModel):
    features: preferences.Features


@router.post("/projects/{identity}/preferences")
def project_preferences(identity: str, req: ProjectFeatures):
    with closing(connect()) as conn:
        initialize(conn)
        project_or_404(conn, identity)
        conn.execute(
            "INSERT INTO project_learning_preferences VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET features_json=excluded.features_json",
            (identity, req.features.model_dump_json()),
        )
        conn.commit()
    return {"saved": True}


class LinkRequest(BaseModel):
    paper_uid: str = Field(min_length=1, max_length=150)


@router.post("/projects/{identity}/papers")
def link(identity: str, req: LinkRequest):
    with closing(connect()) as conn:
        initialize(conn)
        p = project_or_404(conn, identity)
        if not get_paper(conn, req.paper_uid):
            raise HTTPException(404, "论文不在当前空间")
        existing = next(
            (
                r
                for r in projects.list_paper_links(conn, identity)
                if r.paper_uid == req.paper_uid and r.status.value == "active"
            ),
            None,
        )
        if existing:
            return {"linked": True, "duplicate": True}
        try:
            projects.link_paper(
                conn,
                identity,
                p.version,
                PaperLinkCreate(
                    expected_project_version=p.version,
                    paper_uid=req.paper_uid,
                    role="background",
                ),
            )
        except projects.ProjectStoreError as exc:
            raise HTTPException(409, str(exc)) from None
        from app.knowledge.unified import sync_metadata, sync_legacy

        sync_metadata(conn, uid=req.paper_uid, project_id=identity)
        sync_legacy(conn, uid=req.paper_uid, project_id=identity)
        conn.commit()
        return {"linked": True, "duplicate": False}


@router.get("/projects/{identity}")
def project_workspace(identity: str):
    with closing(connect()) as conn:
        initialize(conn)
        p = project_or_404(conn, identity)
        links = projects.list_paper_links(conn, identity)
        papers = [
            get_paper(conn, r.paper_uid) for r in links if r.status.value == "active"
        ]
        row = conn.execute(
            "SELECT features_json FROM project_learning_preferences WHERE project_id=?",
            (identity,),
        ).fetchone()
        notes = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM workspace_records WHERE project_id=? ORDER BY updated_at DESC",
                (identity,),
            )
        ]
        uids = [r["uid"] for r in papers if r]
        sessions = [
            dict(r)
            for r in conn.execute(
                "SELECT id,topic,paper_uid,created_at FROM tutor_sessions ORDER BY created_at DESC LIMIT 500"
            )
            if r["paper_uid"] in uids
            or conn.execute(
                "SELECT 1 FROM project_tutor_sessions WHERE project_id=? AND session_id=?",
                (identity, r["id"]),
            ).fetchone()
        ]
        tasks = [
            dict(r)
            for r in conn.execute(
                "SELECT task_id,kind,status,error_json,updated_at FROM research_async_tasks WHERE project_id=? ORDER BY updated_at DESC LIMIT 50",
                (identity,),
            )
        ]
        return {
            "project": p.model_dump(mode="json"),
            "papers": [r for r in papers if r],
            "records": notes,
            "sessions": sessions,
            "tasks": tasks,
            "features": json.loads(row[0]) if row else preferences.read()["features"],
        }


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=120)):
    needle = q.strip().casefold()
    found = []

    def add(kind, title, body, url):
        if needle in (title + " " + body).casefold():
            found.append(
                {"kind": kind, "title": title, "snippet": body[:180], "url": url}
            )

    with closing(connect()) as conn:
        initialize(conn)
        for r in conn.execute(
            "SELECT uid,title,abstract FROM papers WHERE instr(lower(coalesce(title,'')||' '||coalesce(abstract,'')),?)>0 LIMIT 50",
            (needle,),
        ):
            add(
                "论文",
                r["title"] or r["uid"],
                r["abstract"] or "",
                f"/papers/{quote(r['uid'], safe='')}?tab=reading",
            )
        for r in conn.execute(
            "SELECT * FROM workspace_records WHERE instr(lower(title||' '||body),?)>0 LIMIT 50",
            (needle,),
        ):
            url = (
                f"/research/{r['project_id']}?tab=workbench&record={quote(r['id'], safe='')}"
                if r["project_id"]
                else f"/settings?tab=notebook&record={quote(r['id'], safe='')}"
            )
            add("笔记 / 草稿", r["title"], r["body"], url)
        for r in conn.execute(
            "SELECT id,topic,plan_json FROM tutor_sessions WHERE instr(lower(topic||' '||plan_json),?)>0 LIMIT 50",
            (needle,),
        ):
            add("辅导", r["topic"], r["plan_json"], f"/learn?session={r['id']}")
        for p in projects.list_projects(conn, limit=200)[0]:
            add("课题", p.title, p.research_question, f"/research/{p.id}?tab=workbench")
        for r in conn.execute(
            "SELECT task_id,kind,status,project_id,error_json FROM research_async_tasks"
        ):
            add(
                "任务",
                r["kind"] + " · " + r["status"],
                r["error_json"] or "",
                f"/research/{r['project_id']}?tab=workbench",
            )
    return {"items": found[:50]}


class ImportRequest(BaseModel):
    value: str = Field(min_length=1, max_length=1000)
    project_id: str | None = None


@router.post("/import")
def import_reference(req: ImportRequest):
    from app.config import get_settings

    raw = req.value.strip()
    parsed = urlsplit(raw)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https") or parsed.hostname not in (
            "arxiv.org",
            "www.arxiv.org",
            "doi.org",
            "dx.doi.org",
        ):
            raise HTTPException(
                422, "支持 arXiv、doi.org 链接或论文标识；其他来源请上传 PDF"
            )
        raw = (
            unquote(parsed.path)
            .removeprefix("/abs/")
            .removeprefix("/pdf/")
            .lstrip("/")
            .removesuffix(".pdf")
        )
    raw = re.sub(r"^(arxiv:|doi:)", "", raw, flags=re.I).strip()
    arxiv = re.fullmatch(
        r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", raw, re.I
    )
    doi = re.fullmatch(r"10\.\d{4,9}/\S+", raw, re.I)
    if not arxiv and not doi:
        raise HTTPException(422, "请输入 DOI、arXiv 编号或相应链接")
    uid = (
        arxiv[1]
        if arxiv
        else "doi-" + hashlib.sha256(raw.casefold().encode()).hexdigest()[:32]
    )
    with closing(connect()) as conn:
        initialize(conn)
        if req.project_id:
            project_or_404(conn, req.project_id)
        existing = get_paper(conn, uid)
    if not existing:
        if get_settings().offline_mode:
            raise HTTPException(409, "当前离线，请上传 PDF 或恢复联网后重试")
        try:
            with httpx.Client(
                timeout=20, follow_redirects=False, trust_env=False
            ) as client:
                if arxiv:
                    from app.collector.arxiv import ARXIV_API, _entry_to_doc, _NS

                    response = client.get(ARXIV_API, params={"id_list": uid})
                    response.raise_for_status()
                    entries = ET.fromstring(response.text).findall("a:entry", _NS)
                    doc = _entry_to_doc(entries[0]) if entries else None
                    if not doc or doc.uid != uid:
                        raise ValueError("未找到论文")
                else:
                    response = client.get(
                        "https://api.crossref.org/works/" + quote(raw, safe="")
                    )
                    response.raise_for_status()
                    m = response.json()["message"]
                    dates = m.get("published", {}).get("date-parts", [[0]])
                    doc = PaperDoc(
                        uid=uid,
                        title=(m.get("title") or [raw])[0],
                        abstract=re.sub("<[^>]+>", "", m.get("abstract", "")),
                        authors=[
                            " ".join([a.get("given", ""), a.get("family", "")]).strip()
                            for a in m.get("author", [])
                        ],
                        year=dates[0][0],
                        venue=(m.get("container-title") or [None])[0],
                        source="crossref",
                    )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, ET.ParseError):
            raise HTTPException(
                502, "资料源未返回有效论文，请检查标识或稍后重试；也可上传 PDF"
            ) from None
        with closing(connect()) as conn:
            upsert_paper(conn, doc.model_dump())
    if req.project_id:
        link(req.project_id, LinkRequest(paper_uid=uid))
    return {
        "uid": uid,
        "duplicate": bool(existing),
        "notice": "已添加书目信息。打开论文后获取全文或上传 PDF。",
    }


@router.get("/export")
def export_data(response: Response, project_id: str | None = None):
    response.headers["Cache-Control"] = "no-store"
    with closing(connect()) as conn:
        initialize(conn)
        from app.api.stride import setup

        setup(conn)
        if project_id:
            result = project_workspace(project_id)
            for table in (
                "stride_state",
                "stride_history",
                "stride_cells",
                "stride_candidates",
            ):
                result[table] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM " + table + " WHERE project_id=?", (project_id,)
                    )
                ]
            return result
        data = {}
        # Explicit allowlist excludes API keys, login credentials and session tokens.
        for table in (
            "papers",
            "workspace_records",
            "tutor_sessions",
            "learning_attempts",
            "research_project_versions",
            "research_paper_link_versions",
            "research_plan_versions",
            "research_decision_versions",
            "project_learning_preferences",
            "paper_reading_positions",
            "project_tutor_sessions",
            "stride_state",
            "stride_history",
            "stride_cells",
            "stride_candidates",
        ):
            data[table] = [dict(r) for r in conn.execute("SELECT * FROM " + table)]
        data["profile"] = preferences.public()["profile"]
        return data
