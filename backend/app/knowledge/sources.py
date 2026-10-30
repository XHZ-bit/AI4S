"""Immutable source ingestion, bounded public links and legacy paper bridges."""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import mimetypes
import re
import socket
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.db import projects
from app.knowledge import store
from app.models.research import PaperLinkCreate
from app.storage import save_original
from app.tenancy import data_dir

MAX_BYTES = 50 * 1024 * 1024
EXTENSIONS = {".pdf", ".docx", ".md", ".txt", ".csv", ".xlsx", ".json", ".py", ".js", ".ts", ".tsx", ".jsx", ".cpp", ".c", ".h", ".yaml", ".yml", ".ipynb", ".html"}


def _link_paper(conn, pid, uid):
    if any(x.paper_uid == uid and x.status.value == "active" for x in projects.list_paper_links(conn, pid)):
        return
    p = projects.get_project(conn, pid)
    projects.link_paper(conn, pid, p.version, PaperLinkCreate(expected_project_version=p.version, paper_uid=uid, role="background"))


def ingest(pid, raw, filename, kind=None, *, paper_uid=None, url=None):
    filename = Path(filename.replace("\\", "/")).name[:240] or "source.txt"
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(415, "支持 PDF、DOCX、文本、表格、JSON 和代码文件")
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413, "资料为空或超过 50 MB")
    if kind is None:
        kind = "paper" if suffix == ".pdf" else "results" if suffix in {".csv", ".xlsx", ".json"} else "code" if suffix in {".py", ".js", ".ts", ".tsx", ".jsx", ".cpp", ".c", ".h", ".ipynb"} else "report"
    if kind not in {"paper", "report", "results", "code"}:
        raise HTTPException(422, "资料类型不支持")
    with store.connection(pid) as conn:
        if projects.get_project(conn, pid).status.value == "archived":
            raise HTTPException(409, "请先恢复已归档空间")
    digest = hashlib.sha256(raw).hexdigest()
    asset_id = store.identity(digest, suffix)
    if suffix == ".pdf":
        from app.api.papers import _store
        # Keeps existing library, quota checks and original-file access intact.
        paper_uid = _store(SimpleNamespace(file=io.BytesIO(raw), filename=filename), uid=paper_uid)
    folder = data_dir() / "knowledge" / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (asset_id + (".repo.json" if filename.endswith(".repo.json") else suffix))
    save_original(path, raw)
    media = mimetypes.guess_type(filename)[0] or "text/plain"
    with store.connection(pid) as conn:
        from app.knowledge.unified import register_scope
        if paper_uid:
            _link_paper(conn, pid, paper_uid)
        register_scope(conn, pid)
        conn.execute("INSERT OR IGNORE INTO kw_assets VALUES(?,?,?,?,?,?)", (asset_id, digest, str(path), filename, media, store.now()))
        old = conn.execute("SELECT id FROM kw_sources WHERE project_id=? AND asset_id=? AND removed=0", (pid, asset_id)).fetchone()
        if old:
            return store.source(conn, pid, old[0])
        value = {"id": uuid4().hex, "project_id": pid, "asset_id": asset_id, "version": "sha256:" + digest,
                 "title": Path(filename).stem, "filename": filename, "kind": kind, "media_type": media,
                 "paper_uid": paper_uid, "url": url, "removed": False, "created_at": store.now()}
        conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (value["id"], pid, asset_id, 0, store.encode(value)))
        return value


def attach(pid, paper_uid):
    from app.db.sqlite import get_paper
    with store.connection(pid) as conn:
        paper = get_paper(conn, paper_uid)
        if not paper:
            raise HTTPException(404, "论文不在当前账号的资料库")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", paper_uid):
        raise HTTPException(422, "论文标识不合法")
    path = data_dir() / "pdfs" / (paper_uid + ".pdf")
    if not path.is_file():
        raise HTTPException(409, "原始 PDF 尚未保存，请先下载原文或上传文件")
    return ingest(pid, path.read_bytes(), paper["title"][:180] + ".pdf", "paper", paper_uid=paper_uid, url=paper.get("pdf_url"))


def public_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise HTTPException(422, "请提供公开的 HTTPS 资料链接")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError()
    except (OSError, ValueError):
        raise HTTPException(422, "该链接未指向可访问的公开资料地址") from None
    return url


def download(url, *, max_bytes=MAX_BYTES):
    public_url(url)
    with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
        for _ in range(5):
            with client.stream("GET", url, headers={"User-Agent": "PaperStride/knowledge-workspace"}) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = public_url(urljoin(url, response.headers.get("location", "")))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(413, "外部资料超过允许大小")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get("content-type", ""), url
    raise HTTPException(422, "资料链接重定向次数过多")


def repository(url):
    parsed = urlsplit(public_url(url))
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname != "github.com" or len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts[:2]):
        raise HTTPException(422, "请提供公开 GitHub 仓库地址")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    # A user-selected file at an immutable commit needs no repository API quota.
    if len(parts) > 4 and parts[2] == 'blob' and re.fullmatch(r'[a-fA-F0-9]{40}', parts[3]):
        commit = parts[3].lower()
        selected_path = unquote('/'.join(parts[4:]))
        if '..' in Path(selected_path).parts or Path(selected_path).suffix.lower() not in {'.py', '.md', '.txt'}:
            raise HTTPException(422, '请选择固定版本中的文本或 Python 文件')
        file_url = f'https://raw.githubusercontent.com/{owner}/{repo}/{commit}/' + quote(selected_path, safe='/')
        blob, _, _ = download(file_url, max_bytes=150_000)
        manifest = {'repository': f'https://github.com/{owner}/{repo}', 'commit': commit,
                    'files': [{'path': selected_path, 'text': blob.decode('utf-8', errors='replace'), 'url': file_url, 'hash': hashlib.sha256(blob).hexdigest()}],
                    'coverage': {'selected_files': 1, 'selection': 'explicit_file', 'tree_truncated': False}}
        return store.encode(manifest).encode(), repo + '.repo.json'
    base = f"https://api.github.com/repos/{owner}/{repo}"
    ref = parts[3] if len(parts) > 4 and parts[2] in {"blob", "tree"} else "HEAD"
    raw, _, _ = download(base + "/commits/" + quote(ref, safe=""), max_bytes=3_000_000)
    commit = json.loads(raw)["sha"]
    raw, _, _ = download(base + "/git/trees/" + commit + "?recursive=1", max_bytes=8_000_000)
    tree = json.loads(raw)
    candidates = [r for r in tree.get("tree", []) if r.get("type") == "blob" and r.get("size", 0) < 150_000
                  and Path(r["path"]).suffix.lower() in {".py", ".md", ".txt"}
                  and not any(x in r["path"].casefold() for x in ["test", "vendor", "third_party", "lock", "secret", ".env"])]
    if len(parts) > 4 and parts[2] in {"blob", "tree"}:
        selected_path = unquote("/".join(parts[4:]))
        candidates = [r for r in candidates if r["path"] == selected_path or (parts[2] == "tree" and r["path"].startswith(selected_path.rstrip("/") + "/"))]
        if not candidates:
            raise HTTPException(422, "指定路径中没有可读取的文本或 Python 文件")
    def code_rank(row):
        path = Path(row['path'])
        name = path.name.casefold()
        score = sum(token in name for token in ['network', 'polic', 'actor', 'critic', 'model', 'algorithm', 'ppo', 'residual'])
        return ('readme' not in name, name in {'__init__.py', 'setup.py'}, -score, name.endswith(('_cfg.py', '_config.py')), len(row['path']))
    candidates.sort(key=code_rank)
    documents = [r for r in candidates if Path(r["path"]).suffix.lower() in {".md", ".txt"}][:2]
    code = [r for r in candidates if Path(r["path"]).suffix.lower() == ".py"][:10]
    files = []
    for row in documents + code:
        file_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/" + quote(row["path"], safe="/")
        blob, _, _ = download(file_url, max_bytes=150_000)
        files.append({"path": row["path"], "text": blob.decode("utf-8", errors="replace"), "url": file_url, "hash": hashlib.sha256(blob).hexdigest()})
    manifest = {"repository": f"https://github.com/{owner}/{repo}", "commit": commit, "files": files,
                "coverage": {"selected_files": len(files), "candidate_files": len(candidates), "tree_truncated": bool(tree.get("truncated"))}}
    return store.encode(manifest).encode(), repo + ".repo.json"


def ingest_link(pid, url, kind=None):
    try:
        parsed = urlsplit(url)
        if parsed.hostname == "github.com":
            raw, filename = repository(url)
            return ingest(pid, raw, filename, "code", url=url)
        if parsed.hostname in {"arxiv.org", "www.arxiv.org"} and parsed.path.startswith(("/abs/", "/html/")):
            url = "https://arxiv.org/pdf/" + parsed.path.split("/")[-1]
        raw, media, final_url = download(url)
        filename = unquote(urlsplit(final_url).path.rsplit("/", 1)[-1]) or "source"
        if raw.startswith(b"%PDF-"):
            if not filename.endswith(".pdf"):
                filename += ".pdf"
        elif "html" in media and Path(filename).suffix.lower() not in EXTENSIONS:
            filename += ".html"
        elif Path(filename).suffix.lower() not in EXTENSIONS:
            filename += ".txt"
        return ingest(pid, raw, filename, kind, url=final_url)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(422, "公开资料暂时无法读取，请检查链接或改为上传文件（" + type(exc).__name__ + "）") from None
