"""Space-scoped knowledge records. Original files and parse blocks are reusable."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.api.workbench import project_or_404
from app.db.sqlite import connect


def now():
    return datetime.now(UTC).isoformat()


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def init(conn):
    schema = """
    CREATE TABLE IF NOT EXISTS kw_scopes(id TEXT PRIMARY KEY,kind TEXT NOT NULL,project_id TEXT,title TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_legacy_map(scope_id TEXT NOT NULL,legacy_table TEXT NOT NULL,legacy_id TEXT NOT NULL,
      record_id TEXT NOT NULL,record_table TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(scope_id,legacy_table,legacy_id));
    CREATE TABLE IF NOT EXISTS kw_migrations(name TEXT PRIMARY KEY,data TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_assets(id TEXT PRIMARY KEY,hash TEXT NOT NULL,path TEXT NOT NULL,
      filename TEXT NOT NULL,media_type TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_parses(asset_id TEXT PRIMARY KEY,parser_version TEXT NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_blocks(id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,ordinal INTEGER NOT NULL,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kw_blocks_asset ON kw_blocks(asset_id,ordinal);
    CREATE TABLE IF NOT EXISTS kw_sources(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,asset_id TEXT NOT NULL,
      removed INTEGER NOT NULL DEFAULT 0,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kw_sources_project ON kw_sources(project_id,removed);
    CREATE TABLE IF NOT EXISTS kw_nodes(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,
      hidden INTEGER NOT NULL DEFAULT 0,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kw_nodes_project ON kw_nodes(project_id,source_id,hidden);
    CREATE TABLE IF NOT EXISTS kw_edges(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,
      source TEXT NOT NULL,target TEXT NOT NULL,hidden INTEGER NOT NULL DEFAULT 0,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kw_edges_project ON kw_edges(project_id,source,target);
    CREATE TABLE IF NOT EXISTS kw_evidence(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_history(id INTEGER PRIMARY KEY,project_id TEXT NOT NULL,record_id TEXT NOT NULL,
      kind TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_runs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,source_id TEXT NOT NULL,
      status TEXT NOT NULL,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kw_runs_source ON kw_runs(project_id,source_id);
    CREATE UNIQUE INDEX IF NOT EXISTS kw_one_active_run ON kw_runs(project_id,source_id) WHERE status IN ('queued','running');
    CREATE TABLE IF NOT EXISTS kw_preferences(project_id TEXT PRIMARY KEY,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_extractions(project_id TEXT NOT NULL,source_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
      data TEXT NOT NULL,PRIMARY KEY(project_id,source_id,fingerprint));
    CREATE TABLE IF NOT EXISTS kw_learning(project_id TEXT NOT NULL,node_id TEXT NOT NULL,fingerprint TEXT NOT NULL,
      data TEXT NOT NULL,PRIMARY KEY(project_id,node_id,fingerprint));
    CREATE TABLE IF NOT EXISTS kw_comparisons(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,fingerprint TEXT NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_model_calls(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,run_id TEXT NOT NULL,
      purpose TEXT NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kw_operations(project_id TEXT NOT NULL,operation_key TEXT NOT NULL,status TEXT NOT NULL,
      updated_at TEXT NOT NULL,PRIMARY KEY(project_id,operation_key));
    """
    # executescript implicitly commits an existing transaction. The unified
    # legacy adapter must be able to join the caller's write transaction.
    for statement in schema.split(';'):
        if statement.strip():
            conn.execute(statement)


@contextmanager
def connection(project_id=None, *, allow_library=False):
    conn = connect()
    try:
        init(conn)
        if project_id == 'library' and allow_library:
            pass
        elif project_id is not None:
            project_or_404(conn, project_id)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def preferences(conn, pid):
    row = conn.execute("SELECT data FROM kw_preferences WHERE project_id=?", (pid,)).fetchone()
    return json.loads(row[0]) if row else {"mode": "research", "view": None}


def save_preferences(conn, pid, values):
    result = {**preferences(conn, pid), **values}
    conn.execute("INSERT INTO kw_preferences VALUES(?,?) ON CONFLICT(project_id) DO UPDATE SET data=excluded.data", (pid, encode(result)))
    return result


def source(conn, pid, sid, *, blocks=False, include_removed=False):
    row = conn.execute("SELECT data,removed FROM kw_sources WHERE id=? AND project_id=?", (sid, pid)).fetchone()
    if not row or (row[1] and not include_removed):
        raise HTTPException(404, "资料不在当前研究空间")
    result = json.loads(row[0])
    result["removed"] = bool(row[1])
    run = conn.execute("SELECT data FROM kw_runs WHERE project_id=? AND source_id=? ORDER BY rowid DESC LIMIT 1", (pid, sid)).fetchone()
    result["analysis"] = json.loads(run[0]) if run else None
    if blocks:
        result["blocks"] = source_blocks(conn, result["asset_id"])
    return result


def source_blocks(conn, asset_id):
    return [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_blocks WHERE asset_id=? ORDER BY ordinal", (asset_id,))]


def sources(conn, pid, include_removed=False):
    return [source(conn, pid, r[0], include_removed=include_removed) for r in conn.execute("SELECT id FROM kw_sources WHERE project_id=?" + ("" if include_removed else " AND removed=0") + " ORDER BY rowid", (pid,)).fetchall()]


def update_source(conn, pid, sid, values):
    value = source(conn, pid, sid, include_removed=True)
    value.pop("analysis", None)
    value.update(values)
    conn.execute("UPDATE kw_sources SET removed=?,data=? WHERE id=? AND project_id=?", (int(value["removed"]), encode(value), sid, pid))
    return value


def put_parse(conn, asset_id, result):
    # The immutable asset hash plus parser version keys reusable base parsing.
    conn.execute("INSERT OR REPLACE INTO kw_parses VALUES(?,?,?)", (asset_id, "knowledge-parser-v1", encode(result)))
    conn.execute("DELETE FROM kw_blocks WHERE asset_id=?", (asset_id,))
    for ordinal, item in enumerate(result["blocks"]):
        block = {"ordinal": ordinal, "kind": "text", "heading": "", "page": None, "bbox": None, "metadata": {}, **item}
        block["id"] = identity(asset_id, ordinal, block["kind"], block.get("page"), block.get("bbox"))
        block["ordinal"] = ordinal
        conn.execute("INSERT OR REPLACE INTO kw_blocks VALUES(?,?,?,?)", (block["id"], asset_id, ordinal, encode(block)))


def run(conn, pid, rid):
    row = conn.execute("SELECT data FROM kw_runs WHERE id=? AND project_id=?", (rid, pid)).fetchone()
    if not row:
        raise HTTPException(404, "分析任务不在当前研究空间")
    return json.loads(row[0])


def update_run(conn, pid, rid, **values):
    current = run(conn, pid, rid)
    if current["status"] == "cancelled" and values.get("status") != "cancelled":
        return current
    current.update(values)
    current["updated_at"] = now()
    conn.execute("UPDATE kw_runs SET status=?,data=? WHERE id=? AND project_id=?", (current["status"], encode(current), rid, pid))
    return current


def create_run(conn, pid, sid):
    conn.execute("BEGIN IMMEDIATE")
    source(conn, pid, sid)
    row = conn.execute("SELECT data FROM kw_runs WHERE project_id=? AND source_id=? AND status IN ('queued','running')", (pid, sid)).fetchone()
    if row:
        return json.loads(row[0]), False
    value = {"id": uuid4().hex, "project_id": pid, "source_id": sid, "status": "queued",
             "stages": {"save": "done", "parse": "pending", "extract": "pending", "graph": "pending"},
             "progress": 0.1, "errors": [], "warnings": [], "usage": {}, "created_at": now(), "updated_at": now()}
    conn.execute("INSERT INTO kw_runs VALUES(?,?,?,?,?)", (value["id"], pid, sid, "queued", encode(value)))
    return value, True


def record(conn, table, pid, rid):
    if table not in {"kw_nodes", "kw_edges"}:
        raise ValueError("Invalid record table")
    row = conn.execute(f"SELECT data FROM {table} WHERE id=? AND project_id=?", (rid, pid)).fetchone()
    if not row:
        raise HTTPException(404, "知识内容不在当前研究空间")
    result = json.loads(row[0])
    src = conn.execute("SELECT removed FROM kw_sources WHERE id=? AND project_id=?", (result["source_id"], pid)).fetchone()
    result["source_missing"] = not src or bool(src[0])
    return result


def evidence(conn, pid, ids):
    result = []
    for eid in dict.fromkeys(ids):
        row = conn.execute("SELECT data FROM kw_evidence WHERE id=? AND project_id=?", (eid, pid)).fetchone()
        if row:
            value = json.loads(row[0])
            src = conn.execute("SELECT removed,data FROM kw_sources WHERE id=? AND project_id=?", (value["source_id"], pid)).fetchone()
            value["source_missing"] = not src or bool(src[0])
            if src:
                source_value = json.loads(src[1])
                value["source_title"] = source_value["title"]
                if value.get('source_version') and value['source_version'] != source_value['version']:
                    value['source_changed'] = True
                    value['unresolved'] = True
                block_row = conn.execute("SELECT data FROM kw_blocks WHERE id=? AND asset_id=?", (value["block_id"], source_value["asset_id"])).fetchone()
                if block_row:
                    from app.knowledge.math_content import formula_source
                    asset = conn.execute("SELECT filename FROM kw_assets WHERE id=?", (source_value["asset_id"],)).fetchone()
                    formula = formula_source(pid, value, source_value, json.loads(block_row[0]), pdf=bool(asset and asset[0].lower().endswith('.pdf')))
                    if formula:
                        value["formula"] = formula
            result.append(value)
    return result


def add_evidence(conn, pid, src, block, quote=None, origin="source"):
    text = block.get("text", "")
    if quote and quote not in text:
        raise ValueError("引用与实际来源片段不匹配")
    meta = block.get("metadata") or {}
    value = {"id": identity(pid, src["id"], block["id"], quote or ""), "source_id": src["id"],
             "source_title": src["title"], "block_id": block["id"], "quote": quote or text[:1800],
             "source_version": src["version"], "origin": origin,
             "locator": {"page": block.get("page"), "bbox": block.get("bbox"), "heading": block.get("heading"),
                         "ordinal": block["ordinal"], **{k: meta[k] for k in ["start_line", "end_line", "sheet", "cell_range", "path", "commit", "url"] if k in meta}}}
    conn.execute("INSERT OR REPLACE INTO kw_evidence VALUES(?,?,?,?)", (value["id"], pid, src["id"], encode(value)))
    return value["id"]


def put_record(conn, table, value, *, preserve_user=True, authoritative_fields=()):
    row = conn.execute(f"SELECT data FROM {table} WHERE id=? AND project_id=?", (value["id"], value["project_id"])).fetchone()
    if row:
        old = json.loads(row[0])
        if preserve_user:
            # Analysis cannot silently undo an explicit quality decision.
            if old.get('metadata', {}).get('quality_decision') and 'quality_status' not in authoritative_fields:
                value['quality_status'] = old.get('quality_status', 'candidate')
            for field in old.get("metadata", {}).get("user_fields", []):
                if field not in authoritative_fields:
                    value[field] = old.get(field)
            value["metadata"] = {**old.get("metadata", {}), **value.get("metadata", {})}
            if 'hidden' not in authoritative_fields and (not old.get("metadata", {}).get("superseded") or old.get("metadata", {}).get("user_fields")):
                value["hidden"] = old.get("hidden", False)
            elif any(value.get("metadata", {}).get(k) != old.get("metadata", {}).get(k) for k in ("analysis_run", "block_generation")):
                value["metadata"].pop("superseded", None)
        if value.get('quality_status') in {'withdrawn', 'rejected'}:
            value['hidden'] = True
        if {k: v for k, v in old.items() if k != "version"} == {k: v for k, v in value.items() if k != "version"}:
            return old
        conn.execute("INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)",
                     (value["project_id"], value["id"], table, encode(old), now()))
        value["version"] = old["version"] + 1
    else:
        value["version"] = 1
    if table == "kw_nodes":
        conn.execute("INSERT OR REPLACE INTO kw_nodes VALUES(?,?,?,?,?)", (value["id"], value["project_id"], value["source_id"], int(value.get("hidden", False)), encode(value)))
    else:
        conn.execute("INSERT OR REPLACE INTO kw_edges VALUES(?,?,?,?,?,?,?)", (value["id"], value["project_id"], value["source_id"], value["source"], value["target"], int(value.get("hidden", False)), encode(value)))
    return value


def edit_record(conn, table, pid, rid, expected_version, changes):
    conn.execute("BEGIN IMMEDIATE")
    value = record(conn, table, pid, rid)
    if value["version"] != expected_version:
        raise HTTPException(409, {"message": "内容已有新版本，请刷新后重新修改", "current": value})
    value.pop("source_missing", None)
    before = json.loads(encode(value))
    conn.execute("INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)", (pid, rid, table, encode(value), now()))
    value.update(changes)
    if any(k in changes for k in ("label", "summary", "explanation")):
        value["origin"] = "user"
        value['quality_status'] = 'candidate'
        changes = {**changes, "origin": "user"}
    value["version"] += 1
    value.setdefault("metadata", {})["user_fields"] = sorted(set(value.get("metadata", {}).get("user_fields", [])) | set(changes))
    if value["metadata"].get("merged_members") or value["metadata"].get("merged_into"):
        value["metadata"]["merge_user_fields"] = sorted(set(value["metadata"].get("merge_user_fields", [])) | set(changes))
    if table == 'kw_nodes':
        from app.knowledge.compat import write_fact_version
        write_fact_version(conn, before, value)
    if table == "kw_nodes":
        conn.execute("UPDATE kw_nodes SET data=?,hidden=? WHERE id=? AND project_id=?", (encode(value), int(value.get("hidden", False)), rid, pid))
    else:
        conn.execute("UPDATE kw_edges SET data=?,hidden=? WHERE id=? AND project_id=?", (encode(value), int(value.get("hidden", False)), rid, pid))
    return value


def graph(conn, pid, *, source_id=None, node_id=None, q=None, kind=None, limit=100, include_hidden=False, overview=False):
    args = [pid]
    query = "SELECT data FROM kw_nodes WHERE project_id=?"
    if not include_hidden:
        query += " AND hidden=0"
    if source_id:
        source(conn, pid, source_id, include_removed=True)
        query += " AND source_id=?"
        args.append(source_id)
    nodes = [json.loads(r[0]) for r in conn.execute(query, args)]
    all_edges = [json.loads(r[0]) for r in conn.execute("SELECT data FROM kw_edges WHERE project_id=?" + ("" if include_hidden else " AND hidden=0"), (pid,))]
    if not include_hidden:
        from app.knowledge.unified import active, supported_nodes
        removed_sources = {r[0] for r in conn.execute('SELECT id FROM kw_sources WHERE project_id=? AND removed=1', (pid,))}
        nodes = [n for n in nodes if active(n) and n['source_id'] not in removed_sources]
        all_edges = [e for e in all_edges if active(e) and e['source_id'] not in removed_sources]
        nodes = supported_nodes(nodes, all_edges)
    overview_total = None
    if overview and not any([source_id, node_id, q, kind]):
        active = {r[0] for r in conn.execute("SELECT id FROM kw_sources WHERE project_id=? AND removed=0", (pid,))}
        nodes = [n for n in nodes if n["source_id"] in active]
        overview_total = len(nodes)
        by_id = {n["id"]: n for n in nodes}
        roots = sorted((n for n in nodes if n.get("parent_id") is None), key=lambda n: (n['kind'] not in {'paper', 'report'}, n['label']))[:8]
        selected = {n["id"] for n in roots}
        budget = max(len(roots), min(limit, 32))
        # The overview exposes real research semantics, not just file cards.
        source_order = list(dict.fromkeys(n['source_id'] for n in roots))
        def semantic(n):
            meta = n.get('metadata', {})
            return bool(meta.get('semantic') or meta.get('legacy_id') or meta.get('legacy_fact_id')) and not meta.get('structural')
        for kind_name in ["problem", "method", "module", "concept", "formula"]:
            for sid in source_order:
                local = [n for n in nodes if n["source_id"] == sid and semantic(n) and n['kind'] == kind_name]
                if not local and kind_name == 'module' and not any(n['source_id'] == sid and semantic(n) for n in nodes):
                    local = [n for n in nodes if n['source_id'] == sid and n['kind'] == 'module']
                ranked = sorted(local, key=lambda n: (bool(n.get("parent_id") and by_id.get(n["parent_id"], {}).get("kind") in {"method", "module"}), n["label"]))
                for n in ranked[:1]:
                    if len(selected) < budget:
                        selected.add(n["id"])
        # Bring both ends of a few grounded cross-document relations into view.
        for e in all_edges:
            a, b = by_id.get(e["source"]), by_id.get(e["target"])
            if not a or not b or a["source_id"] == b["source_id"] or not e["evidence_ids"]:
                continue
            missing_ids = {a["id"], b["id"]} - selected
            if len(selected) + len(missing_ids) <= budget:
                selected.update(missing_ids)
        # Keep actual grouping paths where possible; never invent relations.
        for nid in list(selected):
            parent = by_id[nid].get("parent_id")
            if parent in by_id and len(selected) < budget:
                selected.add(parent)
        nodes = [n for n in nodes if n["id"] in selected]
    if node_id:
        record(conn, "kw_nodes", pid, node_id)
        nearby = {node_id}
        for edge in all_edges:
            if node_id in (edge["source"], edge["target"]):
                nearby.update([edge["source"], edge["target"]])
        nodes = [n for n in nodes if n["id"] in nearby]
    if q:
        words = q.casefold().split()
        nodes = [n for n in nodes if all(w in (n["label"] + " " + n["summary"]).casefold() for w in words)]
    if kind:
        nodes = [n for n in nodes if n["kind"] == kind]
    total = overview_total if overview_total is not None else len(nodes)
    roots = {"paper", "report", "code", "results"}
    priority = {"problem": 0, "contribution": 1, "method": 2, "module": 3, "experiment": 4, "finding": 5, "limitation": 6, "formula": 7, "algorithm": 8, "concept": 9}
    nodes.sort(key=lambda n: ((n["kind"] in roots if overview_total is not None else n["kind"] not in roots), not n.get("metadata", {}).get("semantic", False), priority.get(n["kind"], 10), n["label"]))
    nodes = nodes[:limit]
    ids = {n["id"] for n in nodes}
    missing = {r[0] for r in conn.execute("SELECT id FROM kw_sources WHERE project_id=? AND removed=1", (pid,))}
    for n in nodes:
        n["source_missing"] = n["source_id"] in missing
    edges = [e for e in all_edges if e["source"] in ids and e["target"] in ids]
    for e in edges:
        e["source_missing"] = e["source_id"] in missing
    return {"nodes": nodes, "edges": edges, "total_nodes": total, "total_edges": len(all_edges), "truncated": total > limit}


def merge_nodes(conn, pid, ids, label=None):
    if len(set(ids)) < 2:
        raise HTTPException(422, "至少选择两个不同的节点")
    nodes = [record(conn, "kw_nodes", pid, nid) for nid in dict.fromkeys(ids)]
    if any(n.get("metadata", {}).get("merged_members") or n.get("metadata", {}).get("merged_into") for n in nodes):
        raise HTTPException(409, "请先拆分已有合并，再重新选择")
    target = json.loads(encode(nodes[0]))
    target["metadata"]["merged_members"] = json.loads(encode(nodes))
    target["metadata"]["user_fields"] = ["label", "summary", "metadata"]
    target["label"] = label or target["label"]
    target["evidence_ids"] = list(dict.fromkeys(eid for n in nodes for eid in n["evidence_ids"]))
    target["summary"] = "\n\n".join(dict.fromkeys(n["summary"] for n in nodes))
    # Snapshot edges enables exact, space-local undo of merge.
    saved_edges = []
    for row in conn.execute("SELECT data FROM kw_edges WHERE project_id=?", (pid,)).fetchall():
        edge = json.loads(row[0])
        if edge["source"] in ids[1:] or edge["target"] in ids[1:]:
            saved_edges.append(dict(edge))
            edge["source"] = target["id"] if edge["source"] in ids[1:] else edge["source"]
            edge["target"] = target["id"] if edge["target"] in ids[1:] else edge["target"]
            edge["hidden"] = edge["source"] == edge["target"]
            put_record(conn, "kw_edges", edge, preserve_user=False)
    target["metadata"]["merged_edges"] = saved_edges
    for n in nodes[1:]:
        n["metadata"]["merged_into"] = target["id"]
        n["metadata"]["user_fields"] = ["hidden", "metadata"]
        n["hidden"] = True
        put_record(conn, "kw_nodes", n, preserve_user=False)
    return put_record(conn, "kw_nodes", target, preserve_user=False)


def split_node(conn, pid, nid):
    node = record(conn, "kw_nodes", pid, nid)
    members = node.get("metadata", {}).get("merged_members", [])
    if not members:
        raise HTTPException(409, "该节点没有可恢复的合并记录")
    for edge in node["metadata"].get("merged_edges", []):
        current = record(conn, "kw_edges", pid, edge["id"])
        current.pop("source_missing", None)
        conn.execute("INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)", (pid, edge["id"], "kw_edges", encode(current), now()))
        restored = {**current, "source": edge["source"], "target": edge["target"], "version": current["version"] + 1}
        if "hidden" not in current.get("metadata", {}).get("user_fields", []):
            restored["hidden"] = edge["hidden"]
        conn.execute("UPDATE kw_edges SET source=?,target=?,hidden=?,data=? WHERE id=? AND project_id=?", (restored["source"], restored["target"], int(restored["hidden"]), encode(restored), edge["id"], pid))
    for member in members:
        current = record(conn, "kw_nodes", pid, member["id"])
        conn.execute("INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)", (pid, member["id"], "kw_nodes", encode(current), now()))
        for field in current.get("metadata", {}).get("merge_user_fields", []):
            if field != "metadata":
                member[field] = current.get(field)
                member.setdefault("metadata", {}).setdefault("user_fields", [])
                member["metadata"]["user_fields"] = sorted(set(member["metadata"]["user_fields"]) | {field})
        member["version"] = current["version"] + 1
        conn.execute("UPDATE kw_nodes SET hidden=?,data=? WHERE id=? AND project_id=?", (int(member["hidden"]), encode(member), member["id"], pid))
    return {"restored": [n["id"] for n in members]}
