"""Ground source dates and missing resource references without model or file access."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re

from app.knowledge import store


_DATE = re.compile(
    r"(?<!\d)(?P<year>20\d{2}|19\d{2})\s*(?:年|[-/.])\s*(?P<month>\d{1,2})"
    r"\s*(?:月|[-/.])\s*(?P<day>\d{1,2})\s*日?"
    r"(?:[T\s]*(?P<hour>\d{1,2})\s*[:：]\s*(?P<minute>\d{2})(?:\s*[:：]\s*(?P<second>\d{2}))?)?"
)
_DATE_CUE = re.compile(r"截至|截止|更新|记录|日期|\bas\s+of\b|\bupdated?\b|\brecorded?\b|\bdated?\b", re.I)
_CUTOFF = re.compile(r"截至|截止|\bas\s+of\b", re.I)
_PATH = re.compile(
    r"(?<![\w])(?:[A-Za-z]:[/\\]+|\.{1,2}[/\\]+|[/\\]+)?"
    r"[\w@+~.\-]+(?:[/\\]+[\w@+~.\-]+)*"
    r"\.(?:py|pyi|ipynb|json|csv|xlsx?|ya?ml|toml|ini|md|txt|pdf|docx|cpp|cc|c|hpp|h|jsx?|tsx?)\b",
    re.I,
)
_REFERENCE = re.compile(r"^\s*\[(?:[A-Za-z]*\d+)\]")


def _protected(value, field):
    meta = value.get("metadata") or {}
    fields = set(meta.get("user_fields") or [])
    return "metadata" in fields or field in fields or "metadata." + field in fields or meta.get(field + "_user_edited", False)


def _reported_date(blocks):
    candidates = []
    for block in blocks:
        text = block.get("text", "")
        for match in _DATE.finditer(text):
            before = text[max(0, match.start() - 48):match.start()]
            # A range beginning is not the report's observation cutoff.
            if re.match(r"\s*(?:至|到|—|–)", text[match.end():]):
                continue
            cue = list(_DATE_CUE.finditer(before))
            if not cue or re.search(r"计划|预计|预定|将于|\bplanned\b|\bscheduled\b", before[max(0, cue[-1].start() - 12):], re.I):
                continue
            values = match.groupdict()
            try:
                value = datetime(int(values["year"]), int(values["month"]), int(values["day"]),
                                 int(values["hour"] or 0), int(values["minute"] or 0), int(values["second"] or 0))
            except ValueError:
                continue
            has_time = values["hour"] is not None
            nearby = text[max(0, match.start() - 80):min(len(text), match.end() + 100)]
            if has_time:
                if re.search(r"北京时间|中国标准时间|\bUTC\s*\+\s*0?8(?::00)?\b", nearby, re.I):
                    value = value.replace(tzinfo=timezone(timedelta(hours=8)))
                elif re.match(r"\s*(?:Z|UTC)\b", text[match.end():], re.I):
                    value = value.replace(tzinfo=timezone.utc)
                else:
                    offset = re.match(r"\s*([+-])(\d{2}):(\d{2})\b", text[match.end():])
                    if offset and int(offset[2]) < 24 and int(offset[3]) < 60:
                        minutes = (int(offset[2]) * 60 + int(offset[3])) * (-1 if offset[1] == "-" else 1)
                        value = value.replace(tzinfo=timezone(timedelta(minutes=minutes)))
            quote = text[max(0, match.start() - 48):min(len(text), match.end() + 100)].strip()
            rank = (bool(_CUTOFF.search(before)), has_time, block.get("ordinal", 0), match.start())
            candidates.append((rank, {"value": value.isoformat() if has_time else value.date().isoformat(),
                                      "block_id": block["id"], "quote": quote,
                                      "precision": "second" if values["second"] else "minute" if has_time else "date"}))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _normalize_path(path):
    return re.sub(r"/+", "/", path.replace("\\", "/")).removeprefix("./").casefold()


def _paths(text):
    # URLs are resource entrances, not claims that a local file was uploaded.
    text = re.sub(r"https?://[^\s<>\"'`]+", " ", text, flags=re.I)
    return list(dict.fromkeys(m.group().strip(".,;，；。") for m in _PATH.finditer(text)))


def _resource_paths(conn, pid, src, node, blocks):
    block_map = {b["id"]: (index, b) for index, b in enumerate(blocks)}
    selected = {}
    for evidence in store.evidence(conn, pid, node.get("evidence_ids", [])):
        if evidence.get("source_id") != src["id"] or evidence.get("block_id") not in block_map:
            continue
        index, block = block_map[evidence["block_id"]]
        if evidence.get("quote") not in block.get("text", ""):
            continue
        selected[index] = block
        # Text parsers may separate a citation's description and its file list.
        # Extend only into short path-bearing adjacent blocks in the same section.
        for following_index in range(index + 1, min(index + 3, len(blocks))):
            following = blocks[following_index]
            text = following.get("text", "")
            if following.get("heading") != block.get("heading") or _REFERENCE.match(text) or not _paths(text) or len(text) > 1200:
                break
            selected[following_index] = following
    return list(dict.fromkeys(path for _, block in sorted(selected.items()) for path in _paths(block.get("text", ""))))


def _inventory(conn, pid):
    uploaded, repository_paths = set(), set()
    for src in store.sources(conn, pid):
        filename = src.get("filename", "")
        if filename.endswith(".repo.json"):
            # Only files actually fetched in the manifest count, not the tree or URL.
            repository_paths.update(_normalize_path(b.get("metadata", {}).get("path", ""))
                                    for b in store.source_blocks(conn, src["asset_id"])
                                    if b.get("metadata", {}).get("path"))
        elif not src.get("url"):
            uploaded.add(_normalize_path(filename).rsplit("/", 1)[-1])
    return uploaded, repository_paths


def _available(path, uploaded, repository_paths):
    normalized = _normalize_path(path)
    if normalized.rsplit("/", 1)[-1] in uploaded:
        return True
    # A public repository's network.py cannot satisfy a private experiment's
    # network.py merely because they have the same basename.
    if "/" not in normalized or re.match(r"^[a-z]:/", normalized) or normalized.startswith("/"):
        return False
    return normalized in repository_paths


def enrich_context(conn, pid, sid):
    """Add grounded report timestamps/resource availability in one caller transaction.

    This inspects only current-account SQLite records. It never opens a referenced
    path, resolves URLs, calls models, or commits on behalf of the caller.
    Node changes use put_record so corrections and prior versions are retained.
    """
    src = store.source(conn, pid, sid)
    blocks = store.source_blocks(conn, src["asset_id"])
    date = _reported_date(blocks) if src.get("kind") == "report" else None
    result = {"reported_at": None, "nodes_updated": 0, "resources_checked": 0}
    if date and not _protected(src, "reported_at"):
        # An explicitly saved source date is retained unless this helper owns it.
        if not src.get("reported_at") or src.get("reported_at_context"):
            changes = {"reported_at": date["value"], "reported_at_evidence": date, "reported_at_context": True}
            if any(src.get(k) != v for k, v in changes.items()):
                src = store.update_source(conn, pid, sid, changes)
        result["reported_at"] = src.get("reported_at")
    uploaded, repository_paths = _inventory(conn, pid)
    rows = conn.execute("SELECT data FROM kw_nodes WHERE project_id=? AND source_id=?", (pid, sid)).fetchall()
    for row in rows:
        old = json.loads(row[0])
        node = deepcopy(old)
        meta = node.setdefault("metadata", {})
        if date and not meta.get("structural") and node["id"] != store.identity(pid, sid, "root") and not _protected(old, "reported_at"):
            meta.update({"reported_at": date["value"], "reported_at_evidence": date, "reported_at_context": True})
        if node.get("kind") == "resource" and not _protected(old, "missing_source") and not _protected(old, "missing_paths"):
            paths = _resource_paths(conn, pid, src, node, blocks)
            if paths or meta.get("resource_context"):
                missing = [path for path in paths if not _available(path, uploaded, repository_paths)]
                meta.update({"missing_source": bool(missing), "missing_paths": missing,
                             "referenced_paths": paths, "resource_context": True})
                result["resources_checked"] += 1
        if node != old:
            saved = store.put_record(conn, "kw_nodes", node)
            if saved != old:
                result["nodes_updated"] += 1
    return result
