"""Canonical knowledge ledger and bounded account-wide graph projections.

The legacy ledger is an import/input contract, never a second graph read model.
All functions accept the caller's SQLite connection and never commit it.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import quote as urlquote

from fastapi import HTTPException

from app.db import projects
from app.knowledge import store
from app.tenancy import data_dir

LIBRARY = "library"
MIGRATION = "unified-knowledge-v1"
INACTIVE = {"withdrawn", "rejected"}


def decode(raw, default=None):
    try:
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


def legacy_text(value, fallback=""):
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def scopes(conn):
    result = [{"id": LIBRARY, "kind": "library", "project_id": None, "title": "资料库"}]
    for row in conn.execute(
        "SELECT project_id,MAX(version) FROM research_project_versions GROUP BY project_id"
    ):
        p = projects.get_project(conn, row[0])
        if p and p.status.value == "active":
            result.append(
                {"id": p.id, "kind": "project", "project_id": p.id, "title": p.title}
            )
    return result


def require_scope(conn, sid):
    if sid == LIBRARY:
        return scopes(conn)[0]
    from app.api.workbench import project_or_404

    p = project_or_404(conn, sid)
    return {"id": sid, "kind": "project", "project_id": sid, "title": p.title}


def register_scope(conn, sid):
    scope = require_scope(conn, sid)
    conn.execute(
        "INSERT INTO kw_scopes VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title",
        (sid, scope["kind"], scope["project_id"], scope["title"]),
    )
    return scope


def source_for_paper(conn, sid, uid):
    """Reuse native sources; missing originals remain explicitly missing."""
    row = conn.execute(
        "SELECT data FROM kw_sources WHERE project_id=? AND json_extract(data,'$.paper_uid')=? AND removed=0 ORDER BY rowid LIMIT 1",
        (sid, uid),
    ).fetchone()
    previous = decode(row[0]) if row else None
    doc = conn.execute(
        "SELECT * FROM documents WHERE paper_uid=? ORDER BY rowid DESC LIMIT 1", (uid,)
    ).fetchone()
    path = (
        data_dir() / "pdfs" / (uid + ".pdf")
        if re.fullmatch(r"[A-Za-z0-9._-]+", uid)
        else None
    )
    available = bool(
        path
        and path.is_file()
        and not path.is_symlink()
        and path.resolve().is_relative_to(data_dir().resolve())
    )
    busy_asset = (
        previous
        and conn.execute(
            "SELECT 1 FROM kw_runs r JOIN kw_sources s ON s.id=r.source_id WHERE s.asset_id=? AND r.status IN ('running','queued')",
            (previous["asset_id"],),
        ).fetchone()
    )
    if previous and (
        busy_asset
        or not previous.get("legacy_migration")
        or (
            previous.get("legacy_document_id") == (doc["id"] if doc else None)
            and previous.get("original_missing") == (not available)
        )
    ):
        return previous
    paper = conn.execute("SELECT * FROM papers WHERE uid=?", (uid,)).fetchone()
    catalog_missing = paper is None
    if catalog_missing:
        # Old databases can contain orphan proposals; preserve their content
        # without inventing a paper, a binary original or a reliable locator.
        paper = {"title": "历史资料：" + uid, "abstract": "", "pdf_url": None}
    register_scope(conn, sid)
    passages = (
        conn.execute(
            "SELECT * FROM passages WHERE document_id=? ORDER BY ordinal", (doc["id"],)
        ).fetchall()
        if doc
        else []
    )
    blocks = [
        {
            "kind": "text",
            "text": p["text"],
            "heading": p["heading"],
            "page": p["page"],
            "bbox": None,
            "metadata": {"legacy_passage_id": p["id"], "legacy_document_id": doc["id"]},
        }
        for p in passages
    ]
    digest = hashlib.sha256(
        store.encode([uid, [(p["id"], p["text"]) for p in passages]]).encode()
    ).hexdigest()
    if available:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    asset_id = store.identity(digest, ".pdf")
    if not blocks and paper["abstract"]:
        blocks = [
            {
                "kind": "text",
                "text": paper["abstract"],
                "heading": "已保存摘要",
                "page": None,
                "metadata": {"metadata_only": True},
            }
        ]
    conn.execute(
        "INSERT OR IGNORE INTO kw_assets VALUES(?,?,?,?,?,?)",
        (
            asset_id,
            digest,
            str(path) if available else "",
            uid + ".pdf",
            "application/pdf",
            store.now(),
        ),
    )
    parsed = conn.execute(
        "SELECT data FROM kw_parses WHERE asset_id=?", (asset_id,)
    ).fetchone()
    placeholder = (
        parsed
        and decode(parsed[0], {}).get("parser") == "legacy-saved-passages"
        and not any(
            not b.get("metadata", {}).get("metadata_only")
            for b in store.source_blocks(conn, asset_id)
        )
    )
    if not parsed or (placeholder and passages):
        store.put_parse(
            conn,
            asset_id,
            {
                "title": paper["title"],
                "blocks": blocks,
                "parser": "legacy-saved-passages",
                "quality": {"status": "partial"},
            },
        )
    src = {
        **(previous or {}),
        "id": previous["id"] if previous else store.identity(sid, "paper", uid),
        "project_id": sid,
        "asset_id": asset_id,
        "paper_uid": uid,
        "version": "sha256:" + digest,
        "title": paper["title"],
        "filename": uid + ".pdf",
        "kind": "paper",
        "media_type": "application/pdf",
        "removed": False,
        "created_at": store.now(),
        "url": paper["pdf_url"],
        "original_missing": not available,
        "catalog_missing": catalog_missing,
        "parser": "legacy-saved-passages",
        "legacy_migration": MIGRATION,
        "legacy_document_id": doc["id"] if doc else None,
        "quality": {"status": "partial", "original_missing": not available},
    }
    conn.execute(
        "INSERT INTO kw_sources VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET asset_id=excluded.asset_id,data=excluded.data",
        (src["id"], sid, asset_id, 0, store.encode(src)),
    )
    from app.knowledge.extraction import node

    root = node(
        src,
        "root",
        "paper",
        src["title"],
        paper["abstract"] or "",
        [],
        metadata={"structural": True, "legacy_paper_uid": uid},
    )
    root["quality_status"] = "metadata"
    store.put_record(conn, "kw_nodes", root)
    return src


def paper_scopes(conn, uid):
    return [LIBRARY] + [
        s["id"]
        for s in scopes(conn)[1:]
        if any(
            x.paper_uid == uid and x.status.value == "active"
            for x in projects.list_paper_links(conn, s["id"])
        )
    ]


def legacy_rows(conn, uid=None, kid=None):
    sql = "SELECT p.id,p.paper_uid,p.kind,p.payload_json,p.status proposal_status,k.document_id,k.passage_id,k.quote,k.start_offset,k.end_offset,k.layer,k.status,k.checks_json FROM extraction_proposals p LEFT JOIN knowledge k ON k.id=p.id"
    args, where = [], []
    if uid is not None:
        where.append("p.paper_uid=?")
        args.append(uid)
    if kid is not None:
        where.append("p.id=?")
        args.append(kid)
    return [
        dict(r)
        for r in conn.execute(
            sql + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY p.id",
            args,
        )
    ]


def _evidence(conn, sid, src, row, payload):
    text = legacy_text(row["quote"] or payload.get("evidence"))
    passage_id = row["passage_id"] or payload.get("passage_id")
    if not text:
        return [], False
    block = next(
        (
            b
            for b in store.source_blocks(conn, src["asset_id"])
            if text in b.get("text", "")
            and not b.get("metadata", {}).get("metadata_only")
        ),
        None,
    )
    if block:
        return [store.add_evidence(conn, sid, src, block, text)], True
    # A historical quote can be retained without inventing a new PDF locator.
    eid = store.identity(sid, "unresolved-legacy-evidence", row["id"])
    evidence = {
        "id": eid,
        "source_id": src["id"],
        "source_title": src["title"],
        "block_id": "",
        "quote": text,
        "source_version": src["version"],
        "origin": "source",
        "unresolved": True,
        "locator": {
            "legacy_passage_id": passage_id,
            "legacy_document_id": row["document_id"],
        },
    }
    conn.execute(
        "INSERT OR REPLACE INTO kw_evidence VALUES(?,?,?,?)",
        (eid, sid, src["id"], store.encode(evidence)),
    )
    return [eid], False


def sync_legacy(conn, *, uid=None, kid=None, project_id=None):
    """Import finished legacy outcomes in the same transaction as their writer."""
    store.init(conn)
    from app.knowledge.extraction import node, edge
    from app.pipeline.extract import canonical_uid

    changed = skipped = 0
    for row in legacy_rows(conn, uid, kid):
        busy = conn.execute(
            "SELECT 1 FROM kw_runs r JOIN kw_sources s ON s.id=r.source_id WHERE json_extract(s.data,'$.paper_uid')=? AND r.status IN ('running','queued')",
            (row["paper_uid"],),
        ).fetchone()
        raw_payload = decode(row["payload_json"], {})
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        required = (
            ("type", "name")
            if row["kind"] == "entity"
            else ("src_type", "src_name", "dst_type", "dst_name", "rel_type")
        )
        issues = [
            key + ":missing_or_invalid"
            for key in required
            if not legacy_text(payload.get(key))
        ]
        fingerprint = store.identity(MIGRATION, 2, row)
        allowed = paper_scopes(conn, row["paper_uid"])
        targets = (
            [project_id] if project_id in allowed else ([] if project_id else allowed)
        )
        for sid in targets:
            old = conn.execute(
                "SELECT fingerprint,record_id,record_table FROM kw_legacy_map WHERE scope_id=? AND legacy_table='knowledge' AND legacy_id=?",
                (sid, str(row["id"])),
            ).fetchone()
            if old and old[0] == fingerprint:
                skipped += 1
                continue
            if busy and not old:
                skipped += 1
                continue
            src = (
                store.source(
                    conn,
                    sid,
                    store.record(conn, old[2], sid, old[1])["source_id"],
                    include_removed=True,
                )
                if busy
                else source_for_paper(conn, sid, row["paper_uid"])
            )
            ids, located = _evidence(conn, sid, src, row, payload)
            status = (
                "rejected"
                if row["proposal_status"] == "rejected"
                else row["status"] or "legacy_unverified"
            )
            checks = decode(row["checks_json"], {})
            checks = checks if isinstance(checks, dict) else {}
            meta = {
                "legacy_id": row["id"],
                "legacy_table": "knowledge",
                "legacy_payload": payload,
                "legacy_paper_uid": row["paper_uid"],
                "legacy_passage_id": row["passage_id"] or payload.get("passage_id"),
                "legacy_document_id": row["document_id"],
                "legacy_start_offset": row["start_offset"],
                "legacy_end_offset": row["end_offset"],
                "legacy_layer": row["layer"] or "author_claim",
                "legacy_checks": checks,
                "evidence_located": located,
                "source_withdrawn": status in INACTIVE,
                "semantic": True,
                "legacy_input_issues": issues,
                "legacy_payload_raw": row["payload_json"],
            }
            root = store.identity(sid, src["id"], "root")
            if row["kind"] == "entity":
                entity_kind = legacy_text(payload.get("type"), "concept")
                entity_name = legacy_text(payload.get("name"), "未命名历史知识")
                meta["legacy_uid"] = legacy_text(payload.get("uid")) or canonical_uid(
                    entity_kind, entity_name
                )
                value = node(
                    src,
                    ["legacy-claim", row["id"]],
                    entity_kind,
                    entity_name,
                    legacy_text(payload.get("description"))
                    or legacy_text(payload.get("evidence")),
                    ids,
                    parent_id=root,
                    metadata=meta,
                )
                table = "kw_nodes"
                mention = edge(
                    src,
                    root,
                    value["id"],
                    "MENTIONS",
                    "包含知识",
                    "来自该资料的历史抽取记录",
                    ids,
                )
                mention["quality_status"] = status
                mention["hidden"] = status in INACTIVE
                store.put_record(conn, "kw_edges", mention, preserve_user=False)
            else:
                endpoints = []
                for side in ("src", "dst"):
                    raw_kind = payload.get(side + "_type", "concept")
                    kind = legacy_text(raw_kind, "concept")
                    label = legacy_text(payload.get(side + "_name"), "未命名历史知识")
                    key = legacy_text(payload.get(side + "_uid")) or store.identity(
                        raw_kind, label.casefold()
                    )
                    if kind == "paper" and (
                        key == row["paper_uid"] or label == src["title"]
                    ):
                        endpoints.append(root)
                        continue
                    existing = next(
                        (
                            decode(r[0])
                            for r in conn.execute(
                                "SELECT data FROM kw_nodes WHERE source_id=? AND project_id=?",
                                (src["id"], sid),
                            )
                            if decode(r[0]).get("metadata", {}).get("legacy_id")
                            and legacy_text(
                                decode(r[0])
                                .get("metadata", {})
                                .get("legacy_payload", {})
                                .get("type"),
                                "concept",
                            )
                            == kind
                            and legacy_text(
                                decode(r[0])
                                .get("metadata", {})
                                .get("legacy_payload", {})
                                .get("name"),
                                "未命名历史知识",
                            )
                            == label
                        ),
                        None,
                    )
                    if existing:
                        endpoints.append(existing["id"])
                        continue
                    endpoint = node(
                        src,
                        ["legacy-endpoint", key],
                        kind,
                        label,
                        "",
                        [],
                        parent_id=root,
                        metadata={
                            "legacy_uid": legacy_text(payload.get(side + "_uid"))
                            or canonical_uid(kind, label),
                            "legacy_paper_uid": row["paper_uid"],
                            "legacy_endpoint": True,
                        },
                    )
                    endpoint["quality_status"] = "legacy_unverified"
                    store.put_record(conn, "kw_nodes", endpoint)
                    endpoints.append(endpoint["id"])
                    mention = edge(
                        src,
                        root,
                        endpoint["id"],
                        "MENTIONS",
                        "涉及知识",
                        "该来源中的关系涉及此知识",
                        ids,
                    )
                    mention["quality_status"] = "candidate"
                    store.put_record(conn, "kw_edges", mention)
                value = edge(
                    src,
                    *endpoints,
                    legacy_text(payload.get("rel_type"), "UNKNOWN"),
                    legacy_text(payload.get("rel_type"), "未标注关系类型"),
                    legacy_text(payload.get("description"))
                    or legacy_text(payload.get("evidence")),
                    ids,
                )
                value["id"] = store.identity(
                    sid, src["id"], "legacy-relation", row["id"]
                )
                value["metadata"] = meta
                table = "kw_edges"
            value["quality_status"] = status
            value["hidden"] = status in INACTIVE
            # Native user edits in a space remain independent of a library edit.
            store.put_record(conn, table, value)
            conn.execute(
                "INSERT OR REPLACE INTO kw_legacy_map VALUES(?,?,?,?,?,?)",
                (sid, "knowledge", str(row["id"]), value["id"], table, fingerprint),
            )
            changed += 1
    return {"records_imported": changed, "records_unchanged": skipped}


def migrate(conn, project_id=None):
    store.init(conn)
    deferred = False
    for paper in conn.execute("SELECT uid FROM papers").fetchall():
        if conn.execute(
            "SELECT 1 FROM kw_runs r JOIN kw_sources s ON s.id=r.source_id WHERE json_extract(s.data,'$.paper_uid')=? AND r.status IN ('running','queued')",
            (paper[0],),
        ).fetchone():
            deferred = True
            continue
        targets = [project_id] if project_id else paper_scopes(conn, paper[0])
        for sid in targets:
            if sid != LIBRARY and not any(
                x.paper_uid == paper[0] and x.status.value == "active"
                for x in projects.list_paper_links(conn, sid)
            ):
                continue
            source_for_paper(conn, sid, paper[0])
    result = sync_legacy(conn, project_id=project_id)
    sync_audit(conn, project_id=project_id)
    if not deferred:
        sync_metadata(conn, project_id=project_id)
    if project_id is None and not deferred:
        conn.execute(
            "INSERT OR IGNORE INTO kw_migrations VALUES(?,?,?)",
            (MIGRATION, store.encode(result), store.now()),
        )
    return {**result, "model_calls": 0}


def sync_audit(conn, project_id=None):
    """Retain original audit bytes and actors with idempotent record mappings."""
    if project_id in (None, LIBRARY):
        for row in conn.execute("SELECT * FROM audit_events ORDER BY id").fetchall():
            mapped = conn.execute(
                "SELECT record_id FROM kw_legacy_map WHERE scope_id='library' AND legacy_table='knowledge' AND legacy_id=?",
                (str(row["knowledge_id"]),),
            ).fetchone()
            if (
                not mapped
                or conn.execute(
                    "SELECT 1 FROM kw_legacy_map WHERE scope_id='library' AND legacy_table='audit_events' AND legacy_id=?",
                    (str(row["id"]),),
                ).fetchone()
            ):
                continue
            value = dict(row)
            conn.execute(
                "INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)",
                (
                    LIBRARY,
                    mapped[0],
                    "legacy_quality:" + row["action"],
                    store.encode(value),
                    row["created_at"],
                ),
            )
            conn.execute(
                "INSERT INTO kw_legacy_map VALUES(?,?,?,?,?,?)",
                (
                    LIBRARY,
                    "audit_events",
                    str(row["id"]),
                    mapped[0],
                    "kw_history",
                    store.identity(value),
                ),
            )
    for row in conn.execute("SELECT * FROM research_fact_audit ORDER BY id").fetchall():
        if project_id and row["project_id"] != project_id:
            continue
        mapped = conn.execute(
            "SELECT record_id FROM kw_legacy_map WHERE scope_id=? AND legacy_table='research_fact' AND legacy_id=?",
            (row["project_id"], row["fact_id"]),
        ).fetchone()
        if (
            not mapped
            or conn.execute(
                "SELECT 1 FROM kw_legacy_map WHERE scope_id=? AND legacy_table='research_fact_audit' AND legacy_id=?",
                (row["project_id"], str(row["id"])),
            ).fetchone()
        ):
            continue
        value = dict(row)
        conn.execute(
            "INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)",
            (
                row["project_id"],
                mapped[0],
                "legacy_quality:" + row["action"],
                store.encode(value),
                row["created_at"],
            ),
        )
        conn.execute(
            "INSERT INTO kw_legacy_map VALUES(?,?,?,?,?,?)",
            (
                row["project_id"],
                "research_fact_audit",
                str(row["id"]),
                mapped[0],
                "kw_history",
                store.identity(value),
            ),
        )


def sync_metadata(conn, uid=None, project_id=None):
    store.init(conn)
    from app.knowledge.extraction import node, edge

    papers = conn.execute(
        "SELECT * FROM papers" + (" WHERE uid=?" if uid else ""), (uid,) if uid else ()
    ).fetchall()
    for paper in papers:
        allowed = paper_scopes(conn, paper["uid"])
        for sid in (
            [project_id] if project_id in allowed else ([] if project_id else allowed)
        ):
            src = source_for_paper(conn, sid, paper["uid"])
            root = store.identity(sid, src["id"], "root")
            for category in decode(paper["categories_json"], []):
                n = node(
                    src,
                    ["category", category],
                    "concept",
                    category,
                    "论文分类元数据",
                    [],
                    parent_id=root,
                    metadata={"structural": True},
                )
                n["quality_status"] = "metadata"
                store.put_record(conn, "kw_nodes", n)
                e = edge(
                    src, root, n["id"], "IN_CATEGORY", "分类", "来自论文分类元数据", []
                )
                e["quality_status"] = "metadata"
                store.put_record(conn, "kw_edges", e)
            for citation in conn.execute(
                "SELECT dst_uid FROM paper_citations WHERE src_uid=?", (paper["uid"],)
            ):
                other = conn.execute(
                    "SELECT title FROM papers WHERE uid=?", (citation[0],)
                ).fetchone()
                n = node(
                    src,
                    ["citation", citation[0]],
                    "paper",
                    other[0] if other else "arXiv:" + citation[0],
                    "引用元数据，尚未建立正文依据",
                    [],
                    parent_id=root,
                    metadata={
                        "structural": True,
                        "reference_uid": citation[0],
                        "available": bool(other),
                    },
                )
                n["quality_status"] = "metadata"
                store.put_record(conn, "kw_nodes", n)
                e = edge(
                    src,
                    root,
                    n["id"],
                    "CITES",
                    "引用",
                    "来自已保存的文献引用元数据",
                    [],
                )
                e["quality_status"] = "metadata"
                store.put_record(conn, "kw_edges", e)


def active(value):
    return (
        not value.get("hidden")
        and not value.get("source_missing")
        and value.get("quality_status") not in INACTIVE
        and not value.get("metadata", {}).get("source_withdrawn")
    )


def supported_nodes(nodes, edges):
    # Endpoint placeholders are not independent claims. When their only claim
    # is withdrawn/rejected, a structural MENTIONS edge cannot keep them live.
    linked = {
        endpoint
        for e in edges
        if e["kind"] not in {"MENTIONS", "CONTAINS"}
        or e.get("metadata", {}).get("semantic")
        for endpoint in (e["source"], e["target"])
    }
    return [
        n
        for n in nodes
        if not n.get("metadata", {}).get("legacy_endpoint") or n["id"] in linked
    ]


def sync_research_facts(conn, project_id):
    """Join the legacy research writer's transaction; preserve frozen snapshots."""
    from app.knowledge.migration import _migrate_facts

    store.init(conn)
    register_scope(conn, project_id)
    sources_by_link, sources_by_paper, skipped = {}, {}, set()
    for link in projects.list_paper_links(conn, project_id):
        if link.status.value != "active":
            skipped.add(link.id)
            continue
        if conn.execute(
            "SELECT 1 FROM kw_runs r JOIN kw_sources s ON s.id=r.source_id WHERE r.project_id=? AND json_extract(s.data,'$.paper_uid')=? AND r.status IN ('queued','running')",
            (project_id, link.paper_uid),
        ).fetchone():
            # The record will be imported after analysis. Never replace its parse.
            skipped.add(link.id)
            continue
        src = source_for_paper(conn, project_id, link.paper_uid)
        sources_by_link[link.id] = src
        sources_by_paper[link.paper_uid] = src
    report = {"facts_skipped": 0, "facts_imported": 0, "record_sources": 0}
    _migrate_facts(conn, project_id, sources_by_link, sources_by_paper, skipped, report)
    sync_audit(conn, project_id)
    return report


def is_source_root(node):
    """Identify the stored source root, never a same-named legacy paper entity."""
    return bool(node.get("id") and node.get("project_id") and node.get("source_id")) and not node.get("parent_id") and node["id"] == store.identity(
        node["project_id"], node["source_id"], "root"
    )


def source_overview(nodes, all_nodes, sources):
    counts = {}
    for node in all_nodes:
        key = (node["project_id"], node["source_id"])
        counts[key] = counts.get(key, 0) + 1
    by_scope = {}
    for node in nodes:
        if not is_source_root(node) or node["project_id"] != sources[node["source_id"]]["project_id"]:
            continue
        node["metadata"] = {
            **node.get("metadata", {}),
            "source_root": True,
            "child_count": counts[(node["project_id"], node["source_id"])] - 1,
        }
        by_scope.setdefault(node["project_id"], []).append(node)
    groups = sorted(
        by_scope.values(),
        key=lambda group: (group[0]["scope_kind"] != "library", group[0]["scope_label"], group[0]["project_id"]),
    )
    for group in groups:
        group.sort(key=lambda node: (node["source_title"].casefold(), node["source_id"]))
    # One root per source and one source per scope per round. A large collection
    # or many same-named legacy entities cannot consume the whole first page.
    return [group[index] for index in range(max(map(len, groups), default=0)) for group in groups if index < len(group)]


def graph(
    conn,
    *,
    project_id=None,
    q="",
    kind=None,
    paper_uid=None,
    source_id=None,
    node_id=None,
    limit=100,
    offset=0,
    include_hidden=False,
    overview=False,
):
    store.init(conn)
    available = scopes(conn)
    selected_scopes = {
        s["id"]: s for s in available if project_id is None or s["id"] == project_id
    }
    if project_id and not selected_scopes:
        require_scope(conn, project_id)
    sources = {
        r["id"]: decode(r["data"])
        for r in conn.execute("SELECT id,data FROM kw_sources WHERE removed=0")
        if decode(r["data"])["project_id"] in selected_scopes
    }
    all_nodes = []
    for row in conn.execute("SELECT data FROM kw_nodes ORDER BY rowid"):
        n = decode(row[0])
        src = sources.get(n["source_id"])
        if not src or (not include_hidden and not active(n)):
            continue
        scope = selected_scopes[n["project_id"]]
        n.update(
            scope=scope,
            scope_label=scope["title"],
            scope_kind=scope["kind"],
            source_title=src["title"],
            paper_uid=src.get("paper_uid"),
            quality_status=n.get("quality_status", "candidate"),
        )
        n["href"] = (
            ("/research/" + n["project_id"] + "?view=graph&node=" + n["id"])
            if scope["kind"] == "project"
            else "/papers/" + urlquote(src.get("paper_uid") or "") + "?tab=reading"
        )
        all_nodes.append(n)
    valid_ids = {n["id"] for n in all_nodes}
    edges = [decode(r[0]) for r in conn.execute("SELECT data FROM kw_edges")]
    edges = [
        e
        for e in edges
        if e["source"] in valid_ids
        and e["target"] in valid_ids
        and (include_hidden or active(e))
    ]
    if not include_hidden:
        all_nodes = supported_nodes(all_nodes, edges)
        valid_ids = {n["id"] for n in all_nodes}
        edges = [
            e for e in edges if e["source"] in valid_ids and e["target"] in valid_ids
        ]
    matches = [
        n
        for n in all_nodes
        if (
            not q
            or q.casefold() in (n["label"] + " " + n.get("summary", "")).casefold()
        )
        and (not kind or n["kind"] == kind)
        and (not paper_uid or n.get("paper_uid") == paper_uid)
        and (not source_id or n["source_id"] == source_id)
    ]
    if node_id:
        seeds = {
            n["id"]
            for n in matches
            if n["id"] == node_id
            or n.get("paper_uid") == node_id
            or n.get("metadata", {}).get("legacy_uid") == node_id
        }
        nearby = seeds | {
            x
            for e in edges
            if e["source"] in seeds or e["target"] in seeds
            for x in (e["source"], e["target"])
        }
        matches = [n for n in matches if n["id"] in nearby]
    matches.sort(
        key=lambda n: (
            n["kind"] not in {"paper", "report", "code", "results"},
            n["scope_label"],
            n["label"],
            n["id"],
        )
    )
    if overview:
        matches = source_overview(matches, all_nodes, sources)
        limit = min(limit, 50)
    match_ids = {n["id"] for n in matches}
    total_edges = sum(
        e["source"] in match_ids and e["target"] in match_ids for e in edges
    )
    shown = matches[offset : offset + limit]
    ids = {n["id"] for n in shown}
    return {
        "nodes": shown,
        "edges": [e for e in edges if e["source"] in ids and e["target"] in ids],
        "total_nodes": len(matches),
        "total_edges": total_edges,
        "truncated": offset + len(shown) < len(matches),
        "offset": offset,
        "scopes": available,
        **({"overview": True} if overview else {}),
    }


def resolve_legacy_id(conn, rid, table, project_id=None):
    if str(rid).isdigit():
        row = conn.execute(
            "SELECT record_id FROM kw_legacy_map WHERE scope_id=? AND legacy_table='knowledge' AND legacy_id=? AND record_table=?",
            (project_id or LIBRARY, str(rid), table),
        ).fetchone()
        return row[0] if row else rid
    return rid


def detail(conn, nid, project_id=None):
    nid = resolve_legacy_id(conn, nid, "kw_nodes", project_id)
    row = conn.execute("SELECT project_id FROM kw_nodes WHERE id=?", (nid,)).fetchone()
    if not row or (project_id and project_id != row[0]):
        raise HTTPException(404, "知识节点不存在")
    scope = require_scope(conn, row[0])
    node = store.record(conn, "kw_nodes", row[0], nid)
    data = graph(conn, project_id=row[0], node_id=nid, limit=1000)
    shown = next((n for n in data["nodes"] if n["id"] == nid), None)
    if not shown:
        raise HTTPException(404, "知识节点已隐藏或来源已移除")
    if is_source_root(shown):
        source_count = graph(conn, project_id=row[0], source_id=shown["source_id"], limit=0)["total_nodes"]
        shown["metadata"] = {**shown.get("metadata", {}), "source_root": True, "child_count": source_count - 1}
    return {
        "node": shown,
        "edges": data["edges"],
        "neighbors": [n for n in data["nodes"] if n["id"] != nid],
        "evidence": store.evidence(conn, row[0], node["evidence_ids"]),
        "scope": scope,
        "prerequisites": [],
        "resources": [],
        "demos": [],
    }


def ledger(conn, uid=None, project_id=None):
    """Old reading/quality transport, projected exclusively from canonical records."""
    store.init(conn)
    data = graph(
        conn, project_id=project_id, paper_uid=uid, limit=100000, include_hidden=True
    )
    nodes = {n["id"]: n for n in data["nodes"]}
    rows = []
    for table, values in [("kw_nodes", data["nodes"]), ("kw_edges", data["edges"])]:
        for value in values:
            if value.get("metadata", {}).get("structural") or value.get(
                "metadata", {}
            ).get("legacy_endpoint"):
                continue
            meta = value.get("metadata", {})
            if (
                table == "kw_edges"
                and value["kind"] in {"CONTAINS", "MENTIONS", "IN_CATEGORY", "CITES"}
                and not meta.get("legacy_id")
            ):
                continue
            src = store.source(
                conn, value["project_id"], value["source_id"], include_removed=True
            )
            if uid and src.get("paper_uid") != uid:
                continue
            evidence = store.evidence(
                conn, value["project_id"], value.get("evidence_ids", [])
            )
            first = evidence[0] if evidence else {}
            payload = dict(meta.get("legacy_payload") or {})
            payload.update(
                evidence=first.get("quote", ""),
                description=value.get("summary") or value.get("explanation") or "",
            )
            if table == "kw_nodes":
                payload.update(name=value["label"], type=value["kind"], uid=value["id"])
            else:
                a, b = nodes.get(value["source"], {}), nodes.get(value["target"], {})
                payload.update(
                    src_uid=a.get("id"),
                    src_name=a.get("label"),
                    src_type=a.get("kind"),
                    dst_uid=b.get("id"),
                    dst_name=b.get("label"),
                    dst_type=b.get("kind"),
                    rel_type=value["kind"],
                )
            if meta.get("legacy_payload") and value["project_id"] == LIBRARY:
                from app.pipeline.extract import canonical_uid

                for side in ("src", "dst"):
                    original = meta["legacy_payload"]
                    if legacy_text(original.get(side + "_name")):
                        payload[side + "_uid"] = legacy_text(
                            original.get(side + "_uid")
                        ) or canonical_uid(
                            legacy_text(original.get(side + "_type"), "concept"),
                            legacy_text(original.get(side + "_name")),
                        )
            pid = meta.get("legacy_passage_id") or first.get("locator", {}).get(
                "legacy_passage_id"
            )
            rows.append(
                {
                    "id": (meta.get("legacy_id") or value["id"])
                    if value["project_id"] == LIBRARY
                    else value["id"],
                    "canonical_id": value["id"],
                    "scope_id": value["project_id"],
                    "scope_label": next(
                        (
                            s["title"]
                            for s in data["scopes"]
                            if s["id"] == value["project_id"]
                        ),
                        "",
                    ),
                    "paper_uid": src.get("paper_uid"),
                    "kind": "entity" if table == "kw_nodes" else "relation",
                    "payload": payload,
                    "status": value.get("quality_status", "candidate"),
                    "proposal_status": "rejected"
                    if value.get("quality_status") == "rejected"
                    else "pending",
                    "document_id": meta.get("legacy_document_id"),
                    "passage_id": pid,
                    "quote": first.get("quote", ""),
                    "start_offset": meta.get("legacy_start_offset"),
                    "end_offset": meta.get("legacy_end_offset"),
                    "layer": meta.get(
                        "legacy_layer",
                        "teaching"
                        if value["kind"] == "PREREQUISITE_OF"
                        else "author_claim",
                    ),
                    "version": value["version"],
                    "project_id": value["project_id"],
                    "checks": {
                        **meta.get("legacy_checks", {}),
                        "evidence_located": bool(first and not first.get("unresolved")),
                        "structure": meta.get("legacy_checks", {}).get(
                            "structure", not bool(meta.get("legacy_id"))
                        ),
                    },
                    "evidence_url": "/api/learning/evidence/" + str(pid)
                    if pid
                    else None,
                    "evidence": evidence,
                    "href": "/research/"
                    + value["project_id"]
                    + "?view=graph&node="
                    + (value["id"] if table == "kw_nodes" else value["source"])
                    if value["project_id"] != LIBRARY
                    else "/papers/" + str(src.get("paper_uid") or ""),
                }
            )
    return rows


def quality_history(conn):
    store.init(conn)
    result = []
    for row in conn.execute(
        "SELECT * FROM kw_history WHERE kind LIKE 'quality:%' OR kind LIKE 'legacy_quality:%' ORDER BY id DESC LIMIT 200"
    ):
        data = decode(row["data"], {})
        result.append(
            {
                "id": "kw:" + str(row["id"]),
                "knowledge_id": row["record_id"],
                "project_id": row["project_id"],
                "action": row["kind"].split(":", 1)[1],
                "actor": data.get("actor"),
                "reason": data.get("reason"),
                "created_at": row["created_at"],
            }
        )
    for row in conn.execute(
        "SELECT * FROM audit_events a WHERE NOT EXISTS(SELECT 1 FROM kw_legacy_map m WHERE m.legacy_table='audit_events' AND m.legacy_id=CAST(a.id AS TEXT)) ORDER BY id DESC LIMIT 200"
    ):
        result.append(dict(row))
    return sorted(result, key=lambda r: r["created_at"], reverse=True)[:200]


def review_record(
    conn, rid, action, actor, reason, *, project_id=None, expected_version=None
):
    store.init(conn)
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    if str(rid).isdigit():
        sync_legacy(conn, kid=int(rid))
        mapped = conn.execute(
            "SELECT record_id FROM kw_legacy_map WHERE scope_id=? AND legacy_table='knowledge' AND legacy_id=?",
            (project_id or LIBRARY, str(rid)),
        ).fetchone()
        if not mapped:
            raise HTTPException(404, "旧知识标识没有对应的统一记录")
        rid = mapped[0]
    table = (
        "kw_nodes"
        if conn.execute("SELECT 1 FROM kw_nodes WHERE id=?", (rid,)).fetchone()
        else "kw_edges"
    )
    row = conn.execute(
        f"SELECT project_id,data FROM {table} WHERE id=?", (rid,)
    ).fetchone()
    if not row or (project_id is not None and project_id != row[0]):
        raise HTTPException(404, "知识记录不在当前作用域")
    require_scope(conn, row[0])
    value = decode(row[1])
    if expected_version is not None and value["version"] != expected_version:
        raise HTTPException(409, "知识已更新，请刷新后重新审核")
    status = {
        "verify": "human_verified",
        "dispute": "disputed",
        "withdraw": "withdrawn",
        "restore": "candidate",
    }.get(action)
    if status is None:
        raise HTTPException(422, "未知审核操作")
    evidence = store.evidence(conn, row[0], value.get("evidence_ids", []))
    if action == "verify" and value.get("metadata", {}).get("legacy_input_issues"):
        raise HTTPException(
            422, "历史记录存在缺失或无效的类型/名称，请先补正结构再核验"
        )
    if (
        action == "verify"
        and row[0] != LIBRARY
        and value.get("metadata", {}).get("source_withdrawn")
    ):
        raise HTTPException(422, "资料库中的基础依据已撤回，请先恢复依据并重新检查")
    if action == "verify" and (
        value.get("metadata", {}).get("legacy_checks", {}).get("structure") is False
        or not evidence
        or any(e.get("unresolved") or e.get("source_missing") for e in evidence)
    ):
        raise HTTPException(422, "人工核验需要可定位的有效原文依据")
    before = decode(store.encode(value))
    value["quality_status"] = status
    value["hidden"] = action == "withdraw"
    value.setdefault("metadata", {})["quality_decision"] = {
        "action": action,
        "actor": actor,
        "reason": reason,
        "at": store.now(),
    }
    if row[0] == LIBRARY:
        value["metadata"]["source_withdrawn"] = False
    if table == "kw_nodes":
        from app.knowledge.compat import write_fact_version

        write_fact_version(
            conn, before, value, actor=actor, reason=reason, action=action
        )
    store.put_record(conn, table, value, preserve_user=False)
    conn.execute(
        "INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)",
        (
            row[0],
            rid,
            "quality:" + action,
            store.encode({"before": before, "actor": actor, "reason": reason}),
            store.now(),
        ),
    )
    legacy = value["metadata"].get("legacy_id")
    if legacy and row[0] == LIBRARY:
        conn.execute(
            "UPDATE knowledge SET status=?,updated_at=datetime('now') WHERE id=?",
            (status, legacy),
        )
        conn.execute(
            "UPDATE extraction_proposals SET status=? WHERE id=?",
            ("approved" if status == "human_verified" else "pending", legacy),
        )
        audit = conn.execute(
            "INSERT INTO audit_events(knowledge_id,action,actor,reason,before_json,after_json) VALUES(?,?,?,?,?,?)",
            (
                legacy,
                action,
                actor,
                reason,
                store.encode(before),
                store.encode({"status": status}),
            ),
        ).lastrowid
        conn.execute(
            "INSERT INTO kw_legacy_map VALUES(?,?,?,?,?,?)",
            (
                LIBRARY,
                "audit_events",
                str(audit),
                rid,
                "kw_history",
                store.identity(audit, rid, action),
            ),
        )
        for other in conn.execute(
            "SELECT scope_id,record_id,record_table FROM kw_legacy_map WHERE legacy_table='knowledge' AND legacy_id=? AND scope_id!=?",
            (str(legacy), LIBRARY),
        ).fetchall():
            record = store.record(conn, other[2], other[0], other[1])
            record.setdefault("metadata", {})["source_withdrawn"] = (
                status == "withdrawn"
            )
            store.put_record(conn, other[2], record, preserve_user=False)
    if status != "human_verified":
        paper_uid = before.get("metadata", {}).get("legacy_paper_uid")
        guide = (
            conn.execute(
                "SELECT result_json FROM guides WHERE paper_uid=?", (paper_uid,)
            ).fetchone()
            if paper_uid
            else None
        )
        if guide:
            content = decode(guide[0], {})
            content["stale"] = True
            conn.execute(
                "UPDATE guides SET result_json=? WHERE paper_uid=?",
                (store.encode(content), paper_uid),
            )
        for saved in conn.execute("SELECT id,result_json FROM roadmaps").fetchall():
            content = decode(saved[1], {})
            if rid in content.get("knowledge_ids", []) or legacy in content.get(
                "knowledge_ids", []
            ):
                content["stale"] = True
                conn.execute(
                    "UPDATE roadmaps SET result_json=? WHERE id=?",
                    (store.encode(content), saved[0]),
                )
    return {"status": status, "record": store.record(conn, table, row[0], rid)}


def edit_candidate(conn, rid, payload, actor, reason, *, expected_version=None):
    """Apply legacy editor input to a native record without changing its scope."""
    store.init(conn)
    conn.execute("BEGIN IMMEDIATE")
    table = (
        "kw_nodes"
        if conn.execute("SELECT 1 FROM kw_nodes WHERE id=?", (rid,)).fetchone()
        else "kw_edges"
    )
    row = conn.execute(
        f"SELECT project_id,data FROM {table} WHERE id=?", (rid,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "知识记录不存在")
    require_scope(conn, row[0])
    value = decode(row[1])
    if expected_version is not None and value["version"] != expected_version:
        raise HTTPException(409, "知识已更新，请刷新后重新编辑")
    if value.get("quality_status") == "human_verified":
        raise HTTPException(409, "请先撤回已核验记录，再修改内容")
    src = store.source(conn, row[0], value["source_id"])
    text = payload.get("evidence")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(422, "请提供可定位的原文引文")
    block = next(
        (
            b
            for b in store.source_blocks(conn, src["asset_id"])
            if text in b.get("text", "")
            and not b.get("metadata", {}).get("metadata_only")
        ),
        None,
    )
    if not block:
        raise HTTPException(422, "引文必须与当前来源中保存的原文完全一致")
    before = decode(store.encode(value))
    fields = {"evidence_ids", "origin", "quality_status", "hidden", "summary"}
    if table == "kw_nodes":
        label = payload.get("name", value["label"])
        if not isinstance(label, str) or not label.strip():
            raise HTTPException(422, "知识名称不能为空")
        value["label"] = label.strip()
        fields.add("label")
    else:
        for side, key in [("src", "source"), ("dst", "target")]:
            endpoint = store.record(conn, "kw_nodes", row[0], value[key])
            if (
                payload.get(side + "_name", endpoint["label"]) != endpoint["label"]
                or payload.get(side + "_type", endpoint["kind"]) != endpoint["kind"]
            ):
                raise HTTPException(
                    422, "请在图谱中单独修订关系端点，当前编辑器仅修改关系解释和依据"
                )
        value["explanation"] = str(
            payload.get("explanation")
            or payload.get("description")
            or value.get("explanation", "")
        )
        fields.add("explanation")
    value["summary"] = str(payload.get("description") or payload.get("summary") or text)
    value["evidence_ids"] = [store.add_evidence(conn, row[0], src, block, text)]
    value.update(origin="user", quality_status="candidate", hidden=False)
    meta = value.setdefault("metadata", {})
    meta["user_fields"] = sorted(set(meta.get("user_fields", [])) | fields)
    meta["quality_decision"] = {
        "action": "edit",
        "actor": actor,
        "reason": reason,
        "at": store.now(),
    }
    meta["legacy_checks"] = {
        **meta.get("legacy_checks", {}),
        "structure": True,
        "evidence_located": True,
        "semantic": "needs_review",
    }
    if table == "kw_nodes":
        from app.knowledge.compat import write_fact_version

        write_fact_version(conn, before, value, actor=actor, reason=reason)
    store.put_record(conn, table, value, preserve_user=False)
    conn.execute(
        "INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)",
        (
            row[0],
            rid,
            "quality:edit",
            store.encode({"before": before, "actor": actor, "reason": reason}),
            store.now(),
        ),
    )
    return {"status": "candidate", "record": value}
