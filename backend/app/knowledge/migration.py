"""Additive, offline imports of existing project sources and research records.

This module never schedules analysis, calls models, follows document links, or
reads paths mentioned inside a user's report. Existing knowledge sources that
were not created by this migration are left untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import stat

from app.config import get_settings
from app.db import projects
from app.knowledge import extraction, store
from app.storage import save_original
from app.tenancy import data_dir, user_scope

VERSION = "legacy-workspace-v1"


def _latest_facts(conn, pid):
    return [dict(row) for row in conn.execute(
        "SELECT f.* FROM research_fact_versions f JOIN "
        "(SELECT fact_id,MAX(version) version FROM research_fact_versions WHERE project_id=? GROUP BY fact_id) v "
        "ON v.fact_id=f.fact_id AND v.version=f.version WHERE f.project_id=? ORDER BY f.fact_kind,f.fact_id", (pid, pid))]


def _register_original(conn, pid, paper, path):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    asset_id = store.identity(digest, ".pdf")
    existing = conn.execute("SELECT id,data,removed FROM kw_sources WHERE project_id=? AND asset_id=? ORDER BY rowid LIMIT 1", (pid, asset_id)).fetchone()
    if existing:
        value = store.source(conn, pid, existing["id"], include_removed=True)
        active = conn.execute("SELECT 1 FROM kw_runs WHERE project_id=? AND source_id=? AND status IN ('queued','running')", (pid, value["id"])).fetchone()
        writable = not existing["removed"] and not active and value.get("legacy_migration") == VERSION
        return value, False, bool(writable)
    # Never interfere with another source currently producing the shared parse.
    active = conn.execute("SELECT 1 FROM kw_runs r JOIN kw_sources s ON s.id=r.source_id "
                          "WHERE s.asset_id=? AND r.status IN ('queued','running') LIMIT 1", (asset_id,)).fetchone()
    if active:
        return None, False, False
    filename = (paper["title"][:180] or paper["uid"]) + ".pdf"
    source = {"id": store.identity(pid, "legacy-paper", paper["uid"], asset_id), "project_id": pid,
              "asset_id": asset_id, "version": "sha256:" + digest, "title": paper["title"],
              "filename": filename, "kind": "paper", "media_type": "application/pdf", "paper_uid": paper["uid"],
              "url": paper["pdf_url"], "removed": False, "created_at": store.now(), "legacy_migration": VERSION}
    conn.execute("INSERT OR IGNORE INTO kw_assets VALUES(?,?,?,?,?,?)", (asset_id, digest, str(path), filename, "application/pdf", store.now()))
    conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (source["id"], pid, asset_id, 0, store.encode(source)))
    return source, True, True


def _legacy_parse(conn, paper, link):
    document = None
    if link.linked_document_id:
        document = conn.execute("SELECT * FROM documents WHERE id=? AND paper_uid=?", (link.linked_document_id, paper["uid"])).fetchone()
    if document is None:
        document = conn.execute("SELECT * FROM documents WHERE paper_uid=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (paper["uid"],)).fetchone()
    blocks = []
    if document is not None:
        for passage in conn.execute("SELECT * FROM passages WHERE document_id=? ORDER BY ordinal", (document["id"],)):
            meta = json.loads(passage["metadata_json"] or "{}") if "metadata_json" in passage.keys() else {}
            meta.update(legacy_document_id=document["id"], legacy_document_version="sha256:" + document["content_hash"], legacy_passage_id=passage["id"], legacy_migration=VERSION)
            blocks.append({"kind": passage["kind"], "heading": passage["heading"], "text": passage["text"],
                           "page": passage["page"], "bbox": None, "metadata": meta})
    if not blocks:
        return None
    return {"title": paper["title"], "blocks": blocks, "parser": "legacy-saved-passages",
            "quality": {"status": "partial", "block_count": len(blocks), "legacy": True},
            "warnings": ["已复用历史文本解析；尚未完成新版章节、公式与图表解析。"]}


def _partial_run(conn, pid, source, warning):
    rid = store.identity(pid, source["id"], VERSION)
    if conn.execute("SELECT 1 FROM kw_runs WHERE project_id=? AND source_id=?", (pid, source["id"])).fetchone():
        return
    value = {"id": rid, "project_id": pid, "source_id": source["id"], "status": "partial",
             "stages": {"save": "done", "parse": "partial", "extract": "skipped", "graph": "done"},
             "progress": 1, "warnings": [warning], "errors": [], "usage": {"calls": 0},
             "created_at": store.now(), "updated_at": store.now(), "legacy_migration": VERSION}
    conn.execute("INSERT OR IGNORE INTO kw_runs VALUES(?,?,?,?,?)", (rid, pid, source["id"], "partial", store.encode(value)))


def _prepare_source(conn, pid, src, paper, link, path):
    cached = conn.execute("SELECT data FROM kw_parses WHERE asset_id=?", (src["asset_id"],)).fetchone()
    if cached:
        result = json.loads(cached[0])
    else:
        result = _legacy_parse(conn, paper, link)
        if result is None:
            from app.knowledge.parser import parse_source
            result = parse_source(path, "paper", use_docling=False)
            result["warnings"] = list(dict.fromkeys(result.get("warnings", []) + ["历史导入仅进行了本地快速读取，尚未运行新版语义分析。 ".rstrip()]))
        store.put_parse(conn, src["asset_id"], result)
    blocks = store.source_blocks(conn, src["asset_id"])
    src = store.update_source(conn, pid, src["id"], {"quality": {**result.get("quality", {}), "status": "partial", "legacy": True},
                                                      "parser": result.get("parser", "legacy")})
    extraction.structural_graph(conn, src, blocks)
    _partial_run(conn, pid, src, "历史资料已导入；新图谱保留原文结构，选择继续分析可补充知识与公式。")
    return src


def _record_source(conn, pid, fact_rows, evidence_rows):
    """A real export of saved records, clearly distinct from original papers."""
    payload = {"kind": "legacy_research_record_export", "project_id": pid,
               "description": "本资料是已保存的历史研究记录导出，不是论文原文，也不代表重新验证了记录中的陈述。",
               "facts": [json.loads(row["payload_json"]) for row in fact_rows],
               "evidence": [json.loads(row["payload_json"]) for row in evidence_rows]}
    raw = store.encode(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    asset_id, sid = store.identity(digest, ".json"), store.identity(pid, "legacy-records", digest)
    old = conn.execute("SELECT id FROM kw_sources WHERE id=? AND project_id=?", (sid, pid)).fetchone()
    if old:
        return store.source(conn, pid, sid, include_removed=True)
    folder = data_dir() / "knowledge" / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (asset_id + ".json")
    save_original(path, raw)
    source = {"id": sid, "project_id": pid, "asset_id": asset_id, "version": "sha256:" + digest,
              "title": "历史研究记录", "filename": "legacy-research-records.json", "kind": "report", "media_type": "application/json",
              "paper_uid": None, "url": None, "removed": False, "created_at": store.now(),
              "legacy_migration": VERSION, "legacy_record_source": True,
              "quality": {"status": "partial", "legacy": True, "record_export": True}, "parser": "legacy-record-export"}
    conn.execute("INSERT OR IGNORE INTO kw_assets VALUES(?,?,?,?,?,?)", (asset_id, digest, str(path), source["filename"], source["media_type"], store.now()))
    conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (sid, pid, asset_id, 0, store.encode(source)))
    if not conn.execute("SELECT 1 FROM kw_parses WHERE asset_id=?", (asset_id,)).fetchone():
        blocks = [{"kind": "text", "heading": "历史研究记录 " + row["fact_id"], "text": row["payload_json"],
                   "page": None, "bbox": None, "metadata": {"legacy_fact_id": row["fact_id"], "legacy_status": row["status"], "legacy_record_only": True}} for row in fact_rows]
        store.put_parse(conn, asset_id, {"title": source["title"], "blocks": blocks, "parser": "legacy-record-export", "quality": source["quality"], "warnings": [payload["description"]]})
    visible_blocks = [block for block in store.source_blocks(conn, asset_id) if block.get("metadata", {}).get("legacy_status") != "withdrawn"]
    extraction.structural_graph(conn, source, visible_blocks)
    _partial_run(conn, pid, source, payload["description"])
    return source


def _fact_origin(value):
    return {"literature_report": "source", "user_input": "user"}.get(value, "inference")


def _ground_legacy_evidence(conn, pid, ref, source_by_paper):
    """Return a new evidence ID only after verifying an actual stored locator."""
    src = source_by_paper.get(ref.get("paper_uid"))
    if src is None or src.get("removed") or not ref.get("document_id"):
        return None
    doc = conn.execute("SELECT * FROM documents WHERE id=? AND paper_uid=?", (ref["document_id"], ref.get("paper_uid"))).fetchone()
    if doc is None or ref.get("document_version", "").removeprefix("sha256:") != doc["content_hash"]:
        return None
    quote = ref.get("quote") or ""
    passage = None
    if ref.get("passage_id"):
        passage = conn.execute("SELECT * FROM passages WHERE id=? AND document_id=?", (ref["passage_id"], doc["id"])).fetchone()
    elif quote:
        locator = ref.get("locator") or {}
        candidates = conn.execute("SELECT * FROM passages WHERE document_id=? AND (? IS NULL OR page=?) ORDER BY ordinal", (doc["id"], locator.get("page"), locator.get("page"))).fetchall()
        passage = next((p for p in candidates if quote in p["text"]), None)
    if passage is None or (quote and quote not in passage["text"]):
        return None
    quote = quote or passage["text"][:1800]
    if not quote:
        return None
    block = next((b for b in store.source_blocks(conn, src["asset_id"]) if quote in b.get("text", "") and (passage["page"] is None or b.get("page") == passage["page"])), None)
    locator = {**(ref.get("locator") or {}), "page": passage["page"], "heading": passage["heading"],
               "legacy_document_id": doc["id"], "legacy_document_version": ref["document_version"], "legacy_passage_id": passage["id"]}
    if block:
        locator.update(ordinal=block["ordinal"], bbox=block.get("bbox"))
    value = {"id": store.identity(pid, "legacy-evidence", ref["id"], src["id"]), "source_id": src["id"],
             "source_title": src["title"], "block_id": block["id"] if block else "", "quote": quote,
             "source_version": src["version"], "origin": _fact_origin(ref.get("source_kind")), "locator": locator,
             "legacy_migration": VERSION, "legacy_evidence_id": ref["id"], "legacy_source_kind": ref.get("source_kind"),
             "legacy_finding_status": ref.get("finding_status")}
    conn.execute("INSERT OR IGNORE INTO kw_evidence VALUES(?,?,?,?)", (value["id"], pid, src["id"], store.encode(value)))
    return value["id"]


def _summary(fact):
    omitted = {"id", "project_id", "version", "field_evidence", "created_at", "updated_at", "paper_link_id"}
    return "\n".join(f"{key}: {store.encode(value) if isinstance(value, (dict, list)) else value}" for key, value in fact.items() if key not in omitted and value not in (None, "", []))[:12000]


def _migrate_facts(conn, pid, sources_by_link, source_by_paper, skipped_links, report):
    rows = _latest_facts(conn, pid)
    if not rows:
        return
    evidence_rows = conn.execute("SELECT * FROM research_evidence WHERE project_id=? ORDER BY evidence_id", (pid,)).fetchall()
    evidence_map = {r["evidence_id"]: json.loads(r["payload_json"]) for r in evidence_rows}
    facts = {r["fact_id"]: json.loads(r["payload_json"]) for r in rows}
    fallback = None
    imported, pending_edges = {}, []
    for row in rows:
        fact = facts[row["fact_id"]]
        link_id = fact.get("paper_link_id")
        parent_fact_id = fact.get("method_id") or fact.get("experiment_setting_id")
        parent_fact = facts.get(parent_fact_id, {})
        link_id = link_id or parent_fact.get("paper_link_id")
        if not link_id and parent_fact.get("method_id"):
            link_id = facts.get(parent_fact["method_id"], {}).get("paper_link_id")
        if link_id in skipped_links:
            report["facts_skipped"] += 1
            continue
        nid = store.identity(pid, "legacy-fact", row["fact_id"])
        payload_hash = hashlib.sha256(row["payload_json"].encode()).hexdigest()
        old = conn.execute("SELECT data FROM kw_nodes WHERE project_id=? AND id=?", (pid, nid)).fetchone()
        if old and json.loads(old[0]).get("metadata", {}).get("legacy_payload_hash") == payload_hash and json.loads(old[0]).get('metadata', {}).get('legacy_import_revision') == 2:
            conn.execute('INSERT OR IGNORE INTO kw_legacy_map VALUES(?,?,?,?,?,?)', (pid, 'research_fact', row['fact_id'], nid, 'kw_nodes', payload_hash))
            imported[row["fact_id"]] = json.loads(old[0])
            report["facts_skipped"] += 1
            continue
        ids, unresolved = [], []
        for eid in dict.fromkeys(e for field in fact.get("field_evidence", []) for e in field.get("evidence_ids", [])):
            ref = evidence_map.get(eid)
            mapped = _ground_legacy_evidence(conn, pid, ref, source_by_paper) if ref else None
            if mapped:
                ids.append(mapped)
            else:
                unresolved.append(eid)
        src = sources_by_link.get(link_id)
        if src is None and ids:
            evidence = store.evidence(conn, pid, ids)[0]
            src = store.source(conn, pid, evidence["source_id"], include_removed=True)
        origin = _fact_origin(fact.get("source_kind"))
        # User input or unresolved original evidence remains a genuine record export.
        if src is None or not ids or origin == "user":
            if fallback is None:
                fallback = _record_source(conn, pid, rows, evidence_rows)
                report["record_sources"] += 1
            src = fallback
            block = next(b for b in store.source_blocks(conn, src["asset_id"]) if b.get("metadata", {}).get("legacy_fact_id") == row["fact_id"])
            ids.append(store.add_evidence(conn, pid, src, block, origin="user" if origin == "user" else "inference"))
            if origin == "source":
                origin = "inference"
        kind = {"method": "method", "experiment_setting": "experiment", "measurement": "finding"}.get(row["fact_kind"], "concept")
        label = fact.get("name") or fact.get("metric_name") or row["fact_id"]
        metadata = {"legacy_migration": VERSION, "legacy_fact_id": row["fact_id"], "legacy_fact_kind": row["fact_kind"],
                    "legacy_fact_version": row["version"], "legacy_status": row["status"], "legacy_source_kind": fact.get("source_kind"),
                    "legacy_finding_status": fact.get("finding_status"), "legacy_field_evidence": fact.get("field_evidence", []),
                    "legacy_payload_hash": payload_hash, 'legacy_import_revision': 2, "legacy_unverified": row["status"] != "user_confirmed", "verification": "not_revalidated",
                    "legacy_unresolved_evidence": unresolved, "semantic": True, "record_only": bool(src.get("legacy_record_source"))}
        value = extraction.node(src, ["legacy-fact", row["fact_id"]], kind, label, _summary(fact), list(dict.fromkeys(ids)),
                                parent_id=store.identity(pid, src["id"], "root"), origin=origin,
                                research_status="reported_result" if kind == "finding" and fact.get("finding_status") == "reported" else "unspecified", metadata=metadata)
        value["id"] = nid
        value["hidden"] = row["status"] == "withdrawn"
        value['quality_status'] = row['status']
        value['metadata']['source_withdrawn'] = row['status'] == 'withdrawn'
        authoritative = set()
        if old:
            prior = json.loads(old[0])
            prior_meta = prior.get('metadata', {})
            if row['version'] > prior_meta.get('legacy_fact_version', 0):
                authoritative.add('quality_status')
                if row['status'] != prior_meta.get('legacy_status'):
                    authoritative.add('hidden')
                audit = conn.execute('SELECT * FROM research_fact_audit WHERE project_id=? AND fact_id=? AND to_version=? ORDER BY id DESC LIMIT 1', (pid, row['fact_id'], row['version'])).fetchone()
                if audit:
                    value['metadata']['quality_decision'] = {'action': audit['action'], 'actor': audit['actor'], 'reason': audit['reason'], 'at': audit['created_at']}
                    if audit['action'] == 'content_revision':
                        before_fact = json.loads(audit['before_json'])
                        after_fact = json.loads(audit['after_json'])
                        field = 'metric_name' if row['fact_kind'] == 'measurement' else 'name'
                        if before_fact.get(field) != after_fact.get(field):
                            authoritative.add('label')
                        if row['fact_kind'] == 'method' and before_fact.get('summary') != after_fact.get('summary'):
                            authoritative.add('summary')
                            value['summary'] = after_fact.get('summary') or ''
        value = store.put_record(conn, "kw_nodes", value, authoritative_fields=authoritative)
        conn.execute('INSERT INTO kw_legacy_map VALUES(?,?,?,?,?,?) ON CONFLICT(scope_id,legacy_table,legacy_id) DO UPDATE SET fingerprint=excluded.fingerprint', (pid, 'research_fact', row['fact_id'], nid, 'kw_nodes', payload_hash))
        imported[row["fact_id"]] = value
        contains = extraction.edge(src, value["parent_id"], nid, "CONTAINS", "历史研究记录", "保留历史来源与审核状态，未重新进行模型核验。", value["evidence_ids"], origin=origin)
        contains["hidden"] = value["hidden"]
        contains["metadata"] = {"legacy_migration": VERSION}
        store.put_record(conn, "kw_edges", contains)
        if parent_fact_id:
            pending_edges.append((parent_fact_id, value))
        report["facts_imported"] += 1
    for parent_id, value in pending_edges:
        parent = imported.get(parent_id)
        if not parent:
            continue
        src = store.source(conn, pid, value["source_id"], include_removed=True)
        edge = extraction.edge(src, parent["id"], value["id"], "EVALUATED_BY" if value["kind"] == "experiment" else "REPORTS",
                               "实验设置" if value["kind"] == "experiment" else "报告测量", "来自已保存的历史研究记录关联。", value["evidence_ids"], origin=value["origin"])
        edge["hidden"] = parent["hidden"] or value["hidden"]
        edge["metadata"] = {"legacy_migration": VERSION}
        store.put_record(conn, "kw_edges", edge)


def migrate_workspace(project_id=None):
    """Import the current account/root scope without invoking analysis services."""
    report = {"projects": 0, "sources_imported": 0, "sources_skipped": 0, "facts_imported": 0, "facts_skipped": 0, "record_sources": 0, "warnings": [], "model_calls": 0}
    root = data_dir().resolve()
    if not (root / "atlas.db").is_file():
        return report
    with store.connection() as conn:
        if project_id:
            project = projects.get_project(conn, project_id)
            items = [project] if project else []
        else:
            rows = conn.execute("SELECT project_id,MAX(version) version FROM research_project_versions GROUP BY project_id ORDER BY project_id").fetchall()
            items = [projects.get_project(conn, row["project_id"]) for row in rows]
        for project in items:
            if not project or project.status.value != "active":
                continue
            pid = project.id
            report["projects"] += 1
            sources_by_link, source_by_paper, skipped_links = {}, {}, set()
            for link in projects.list_paper_links(conn, pid):
                if link.status.value != "active":
                    skipped_links.add(link.id)
                    continue
                uid = link.paper_uid
                if not re.fullmatch(r"[A-Za-z0-9._-]+", uid):
                    report["warnings"].append({"project_id": pid, "paper_uid": uid, "reason": "论文标识不合法，未读取文件"})
                    skipped_links.add(link.id)
                    continue
                path = (root / "pdfs" / (uid + ".pdf")).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    report["warnings"].append({"project_id": pid, "paper_uid": uid, "reason": "原始 PDF 缺失或不属于当前账号资料目录"})
                    continue
                paper = conn.execute("SELECT * FROM papers WHERE uid=?", (uid,)).fetchone()
                if paper is None:
                    continue
                src, fresh, writable = _register_original(conn, pid, paper, path)
                if not writable:
                    if src is None:
                        skipped_links.add(link.id)
                        report['sources_skipped'] += 1
                        continue
                    if conn.execute("SELECT 1 FROM kw_runs WHERE project_id=? AND source_id=? AND status IN ('queued','running')", (pid, src['id'])).fetchone():
                        skipped_links.add(link.id)
                        report['sources_skipped'] += 1
                        continue
                    sources_by_link[link.id] = src
                    source_by_paper[uid] = src
                    report["sources_skipped"] += 1
                    continue
                if fresh:
                    src = _prepare_source(conn, pid, src, paper, link, path)
                    report["sources_imported"] += 1
                else:
                    report["sources_skipped"] += 1
                sources_by_link[link.id] = src
                source_by_paper[uid] = src
            _migrate_facts(conn, pid, sources_by_link, source_by_paper, skipped_links, report)
        from app.knowledge.unified import migrate as migrate_ledger
        report["unified"] = migrate_ledger(conn, project_id)
    return report


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _registered_accounts(root):
    identity = root / "identity.db"
    if not identity.exists():
        return None
    if _is_link(identity):
        raise ValueError("身份数据库不能是链接文件")
    with closing(sqlite3.connect(identity.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM users") if re.fullmatch(r"[a-f0-9]{32}", row[0])}


def _relative_asset(path, root):
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if not relative.parts or relative.parts[0] not in {"pdfs", "knowledge"}:
        return None
    return relative


def _relocate_assets(conn, root, old_root):
    """Explicitly rebase verified paths after the caller copied original files.

    Every asset is validated before any path update. Account scopes are passed
    separately, so an account's paths cannot resolve into another account.
    """
    if conn.execute("SELECT 1 FROM kw_runs WHERE status IN ('queued','running') LIMIT 1").fetchone():
        raise ValueError("资料分析仍在排队或运行，暂不调整原文件路径")
    if conn.execute("SELECT 1 FROM kw_operations WHERE status='running' LIMIT 1").fetchone():
        raise ValueError("知识生成仍在运行，暂不调整原文件路径")
    changes = []
    root, old_root = root.resolve(), old_root.resolve()
    for row in conn.execute("SELECT id,path,hash FROM kw_assets"):
        if not row['path']:
            # Imported historical metadata may have no original binary.
            continue
        previous = Path(row["path"])
        if not previous.is_absolute():
            raise ValueError("发现相对的原文件路径，未自动推测其位置：" + row["id"])
        previous = previous.resolve()
        relative = _relative_asset(previous, root)
        already_current = relative is not None
        if relative is None:
            relative = _relative_asset(previous, old_root)
        if relative is None:
            raise ValueError("原文件路径不属于所选账号的新旧资料目录：" + row["id"])
        candidate = root / relative
        if not candidate.is_file() or _is_link(candidate) or not candidate.resolve().is_relative_to(root):
            raise ValueError("目标原文件缺失或指向目录之外，未修改路径：" + row["id"])
        digest = hashlib.sha256()
        with candidate.open("rb") as reader:
            while chunk := reader.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != row["hash"]:
            raise ValueError("目标原文件校验不一致，未修改路径：" + row["id"])
        if not already_current:
            changes.append((str(candidate.resolve()), row["id"]))
    for path, asset_id in changes:
        conn.execute("UPDATE kw_assets SET path=? WHERE id=?", (path, asset_id))
    return {"verified": conn.execute("SELECT COUNT(*) FROM kw_assets").fetchone()[0], "relocated": len(changes)}


def migrate_site(root: Path, project_id=None, *, account_ids=None, include_root=True, relocate_from: Path | None = None):
    """Visit only the explicitly selected root and valid account directories."""
    root = root.absolute()
    if not root.is_dir() or _is_link(root):
        raise ValueError("请选择存在的、非链接的资料目录")
    if account_ids is not None and any(not re.fullmatch(r"[a-f0-9]{32}", uid) for uid in account_ids):
        raise ValueError("账号筛选必须使用 32 位十六进制账号标识")
    registered = _registered_accounts(root)
    scopes = [("root", None)] if include_root and (root / "atlas.db").is_file() else []
    skipped_scopes = []
    users = root / "users"
    if users.is_dir() and not _is_link(users):
        for child in sorted(users.iterdir()):
            if not re.fullmatch(r"[a-f0-9]{32}", child.name) or not child.is_dir() or _is_link(child) or not (child / "atlas.db").is_file():
                continue
            if registered is not None and child.name not in registered:
                skipped_scopes.append({"scope": child.name, "reason": "not_registered"})
                continue
            if account_ids is not None and child.name not in account_ids:
                skipped_scopes.append({"scope": child.name, "reason": "not_selected"})
                continue
            scopes.append((child.name, {"id": child.name}))
    saved = {key: os.environ.get(key) for key in ("DATA_DIR", "ACCESS_MODE")}
    result = {"migration": VERSION, "scopes": [], "skipped_scopes": skipped_scopes, "model_calls": 0}
    try:
        os.environ["DATA_DIR"] = str(root)
        os.environ["ACCESS_MODE"] = "local"
        get_settings.cache_clear()
        for name, user in scopes:
            with user_scope(user):
                relocation = None
                if relocate_from is not None:
                    old_scope = relocate_from / "users" / name if user else relocate_from
                    with store.connection() as conn:
                        relocation = _relocate_assets(conn, data_dir(), old_scope)
                value = {"scope": name, **migrate_workspace(project_id)}
                if relocation is not None:
                    value["asset_paths"] = relocation
                result["scopes"].append(value)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
    return result
