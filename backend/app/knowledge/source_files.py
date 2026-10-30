"""Resolve a parsed representation to its exact immutable original PDF.

``documents.content_hash`` versions parsed content; it is not necessarily a hash
of PDF bytes. Legacy bridge representations can be matched by recomputing their
deterministic digest from saved parse blocks. No GET repairs or rewrites data.
"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import stat

from app.knowledge import store
from app.tenancy import data_dir


class DocumentFileError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DocumentFile:
    path: Path
    sha256: str
    document_id: str
    representation_hash: str


def bridge_digest(src, result, blocks):
    return hashlib.sha256(store.encode([src["version"], "knowledge-parser-v1", result.get("parser"), blocks]).encode()).hexdigest()


def bind_document_file(conn, document_id, src, representation_hash):
    """Write an explicit mapping only while publishing a new parse version."""
    conn.execute("""CREATE TABLE IF NOT EXISTS document_source_files(
      document_id TEXT PRIMARY KEY,paper_uid TEXT NOT NULL,source_id TEXT NOT NULL,
      asset_id TEXT NOT NULL,source_file_sha256 TEXT NOT NULL,representation_hash TEXT NOT NULL)""")
    row = conn.execute("SELECT hash FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()
    if row:
        conn.execute("INSERT OR REPLACE INTO document_source_files VALUES(?,?,?,?,?,?)",
                     (document_id, src["paper_uid"], src["id"], src["asset_id"], row[0], representation_hash))


def _safe_file(path):
    root = data_dir().resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        return None
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError:
        return None
    if not relative.parts or relative.parts[0] not in {"pdfs", "knowledge"} or ".." in relative.parts:
        return None
    current = root
    for part in relative.parts:
        current /= part
        try:
            info = current.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            return None
    return candidate if candidate.is_file() and candidate.resolve().is_relative_to(root) else None


def _file_hash(path, cache):
    info = path.stat()
    key = (str(path), info.st_size, info.st_mtime_ns)
    if key not in cache:
        digest = hashlib.sha256()
        with path.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
        cache[key] = digest.hexdigest()
    return cache[key]


def _bridge_matches(conn, src, parsed, blocks, document_id, representation):
    if bridge_digest(src, parsed, blocks) == representation:
        return True
    # On-demand formula transcription may enrich current reusable blocks after
    # the document snapshot was published. Recover its earlier text/metadata by
    # a unique saved parser block reference, then require an exact full digest.
    # Matching names, pages or snippets alone can never authorize another PDF.
    def reference(meta):
        return next(((key, meta[key]) for key in ("source_block_id", "docling_ref", "block_id") if isinstance(meta.get(key), str)), None)

    snapshots = {}
    for row in conn.execute("SELECT heading,page,kind,text,metadata_json FROM passages WHERE document_id=?", (document_id,)):
        metadata = json.loads(row[4] or "{}")
        ref = reference(metadata)
        if ref:
            snapshots.setdefault((ref, row[0], row[1], row[2]), []).append((row[3], metadata))
    restored = deepcopy(blocks)
    for block in restored:
        ref = reference(block.get("metadata", {}))
        matches = snapshots.get((ref, block.get("heading", ""), block.get("page"), block["kind"]), []) if ref else []
        if len(matches) == 1:
            block["text"], block["metadata"] = matches[0]
    return bridge_digest(src, parsed, restored) == representation


def resolve_document_file(conn, uid, document_id, *, file_sha256=None, hashes=None):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", uid):
        raise DocumentFileError("论文标识不合法", 422)
    row = conn.execute("SELECT d.content_hash FROM documents d JOIN papers p ON p.uid=d.paper_uid WHERE d.id=? AND d.paper_uid=?", (document_id, uid)).fetchone()
    if row is None:
        raise DocumentFileError("文档版本不存在", 404)
    representation = row[0]
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    candidates = []
    original = data_dir() / "pdfs" / (uid + ".pdf")
    if re.fullmatch(r"[a-f0-9]{64}", representation):
        candidates.append((original, representation))
    if "document_source_files" in names and "kw_assets" in names:
        mapped = conn.execute("SELECT a.path,a.hash FROM document_source_files f JOIN kw_assets a ON a.id=f.asset_id "
                              "WHERE f.document_id=? AND f.paper_uid=? AND f.representation_hash=? AND f.source_file_sha256=a.hash",
                              (document_id, uid, representation)).fetchall()
        candidates.extend((Path(r[0]), r[1]) for r in mapped)
    if {"kw_sources", "kw_assets"} <= names:
        for source_id, raw in conn.execute("SELECT id,data FROM kw_sources"):
            src = json.loads(raw)
            if src.get("paper_uid") != uid or src.get("kind") != "paper":
                continue
            asset = conn.execute("SELECT path,hash FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()
            if not asset:
                continue
            exact = asset[1] == representation
            if not exact and {"kw_parses", "kw_blocks"} <= names:
                parse = conn.execute("SELECT data FROM kw_parses WHERE asset_id=?", (src["asset_id"],)).fetchone()
                if parse:
                    blocks = store.source_blocks(conn, src["asset_id"])
                    exact = _bridge_matches(conn, src, json.loads(parse[0]), blocks, document_id, representation)
            if exact:
                candidates.append((Path(asset[0]), asset[1]))
    cache = hashes if hashes is not None else {}
    for candidate, expected in candidates:
        safe = _safe_file(candidate)
        if safe is None:
            continue
        try:
            actual = _file_hash(safe, cache)
        except OSError:
            continue
        if actual != expected:
            continue
        if file_sha256 is not None and file_sha256 != actual:
            raise DocumentFileError("请求的 PDF 文件版本与此文档绑定的原文件不一致")
        return DocumentFile(safe, actual, document_id, representation)
    present = _safe_file(original) is not None or any(_safe_file(path) is not None for path, _ in candidates)
    if present:
        raise DocumentFileError("此解析版本对应的原始 PDF 无法核对；当前保存的 PDF 不能代替该历史版本")
    raise DocumentFileError("此文档对应的原始 PDF 尚未保存或已缺失", 404)


def read_document_file(conn, uid, document_id, *, file_sha256=None):
    resolved = resolve_document_file(conn, uid, document_id, file_sha256=file_sha256)
    try:
        raw = resolved.path.read_bytes()
    except OSError as exc:
        raise DocumentFileError("原始 PDF 文件暂时无法读取", 404) from exc
    if hashlib.sha256(raw).hexdigest() != resolved.sha256:
        raise DocumentFileError("PDF 原文件在读取期间发生变化，请重新打开")
    return resolved, raw
