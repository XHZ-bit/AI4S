"""Version-aware source-to-plan/snapshot edges for targeted impact lookup."""

import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_dependency_edges (
 project_id TEXT NOT NULL, target_kind TEXT NOT NULL, target_id TEXT NOT NULL,
 target_version INTEGER NOT NULL, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
 source_version TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(target_kind,target_id,target_version,source_kind,source_id,source_version));
CREATE INDEX IF NOT EXISTS idx_research_dependency_source
 ON research_dependency_edges(project_id,source_kind,source_id);
CREATE TABLE IF NOT EXISTS research_dependency_index_meta (
 version INTEGER PRIMARY KEY, built_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS research_impact_checkpoints (
 checkpoint_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
 input_fingerprint TEXT NOT NULL, report_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 UNIQUE(project_id,input_fingerprint));
CREATE INDEX IF NOT EXISTS idx_research_impact_checkpoints_project
 ON research_impact_checkpoints(project_id,created_at,checkpoint_id);
"""


def _add(edges, kind, identity, version=""):
    if identity:
        edges.add((kind, str(identity), str(version)))


def _expand_evidence(conn, edges, evidence_id):
    _add(edges, "evidence", evidence_id)
    row = conn.execute("SELECT payload_json FROM research_evidence WHERE evidence_id=?",
                       (evidence_id,)).fetchone()
    if not row:
        return
    value = json.loads(row["payload_json"])
    _add(edges, "paper", value.get("paper_uid"))
    _add(edges, "document", value.get("document_id"), value.get("document_version") or "")


def _expand_fact(conn, edges, fact_id, version=None):
    _add(edges, "fact", fact_id, version if version is not None else "")
    if version is None:
        row = conn.execute("SELECT payload_json FROM research_fact_versions WHERE fact_id=? "
                           "ORDER BY version DESC LIMIT 1", (fact_id,)).fetchone()
    else:
        row = conn.execute("SELECT payload_json FROM research_fact_versions "
                           "WHERE fact_id=? AND version=?", (fact_id, version)).fetchone()
    if not row:
        return
    value = json.loads(row["payload_json"])
    link_id = value.get("paper_link_id")
    _add(edges, "paper_link", link_id)
    if link_id:
        link = conn.execute("SELECT paper_uid FROM research_paper_link_versions "
                            "WHERE link_id=? ORDER BY version DESC LIMIT 1", (link_id,)).fetchone()
        if link:
            _add(edges, "paper", link["paper_uid"])
    for field in value.get("field_evidence", []):
        for evidence_id in field.get("evidence_ids", []):
            _expand_evidence(conn, edges, evidence_id)


def _plan_edges(conn, plan):
    edges = set()
    _add(edges, "project", plan.get("project_id"))
    for fact_id in [plan.get("selected_method_id"),
                    *plan.get("selected_experiment_setting_ids", []),
                    *plan.get("target_measurements", [])]:
        _expand_fact(conn, edges, fact_id)
    selected_settings = set(plan.get("selected_experiment_setting_ids", []))
    if selected_settings:
        for row in conn.execute(
            "SELECT f.fact_id,f.version,f.payload_json FROM research_fact_versions f "
            "JOIN (SELECT fact_id,MAX(version) version FROM research_fact_versions "
            "WHERE project_id=? AND fact_kind='measurement' GROUP BY fact_id) latest "
            "ON latest.fact_id=f.fact_id AND latest.version=f.version",
            (plan["project_id"],),
        ):
            if json.loads(row["payload_json"]).get("experiment_setting_id") in selected_settings:
                _expand_fact(conn, edges, row["fact_id"])
    for step in plan.get("steps", []):
        for evidence_id in step.get("evidence_ids", []):
            _expand_evidence(conn, edges, evidence_id)
    return edges


def _snapshot_edges(conn, snapshot):
    edges = set()
    _add(edges, "project", snapshot["project_id"])
    _add(edges, "project", snapshot["project_id"], snapshot["frozen_project_version"])
    decision = snapshot["frozen_decision"]
    _add(edges, "decision", decision["id"], decision["version"])
    _add(edges, "plan", snapshot["plan"]["id"], snapshot["plan"]["version"])
    for step in snapshot["plan"].get("steps", []):
        for evidence_id in step.get("evidence_ids", []):
            _expand_evidence(conn, edges, evidence_id)
    for fact in snapshot.get("frozen_facts", []):
        _expand_fact(conn, edges, fact["id"], fact["version"])
    for document in snapshot.get("frozen_documents", []):
        _add(edges, "paper_link", document["paper_link_id"])
        _add(edges, "paper", document["paper_uid"])
        _add(edges, "document", document["document_id"], document["document_version"])
    row = conn.execute("SELECT payload_json FROM research_decision_versions "
                       "WHERE decision_id=? AND version=?",
                       (decision["id"], decision["version"])).fetchone()
    if row:
        for evidence_id in json.loads(row["payload_json"]).get("evidence_ids", []):
            _expand_evidence(conn, edges, evidence_id)
    return edges


def _write_edges(conn, project_id, target_kind, target_id, target_version, edges):
    conn.execute("DELETE FROM research_dependency_edges WHERE target_kind=? "
                 "AND target_id=? AND target_version=?",
                 (target_kind, target_id, target_version))
    conn.executemany("INSERT INTO research_dependency_edges "
                     "(project_id,target_kind,target_id,target_version,source_kind,source_id,source_version) "
                     "VALUES(?,?,?,?,?,?,?)",
                     [(project_id, target_kind, target_id, target_version, kind, identity, version)
                      for kind, identity, version in sorted(edges)])


def index_plan(conn, plan):
    value = plan if isinstance(plan, dict) else plan.model_dump(mode="json")
    _write_edges(conn, value["project_id"], "plan", value["id"], value["version"],
                 _plan_edges(conn, value))


def index_snapshot(conn, snapshot):
    value = snapshot if isinstance(snapshot, dict) else snapshot.model_dump(mode="json")
    _write_edges(conn, value["project_id"], "snapshot", value["id"],
                 value["snapshot_version"], _snapshot_edges(conn, value))


def refresh_live_plan_edges(conn, project_id):
    """Rebuild live fact links; frozen snapshot links retain their original versions."""
    for row in conn.execute("SELECT payload_json FROM research_plan_versions WHERE project_id=?",
                            (project_id,)).fetchall():
        index_plan(conn, json.loads(row["payload_json"]))


def init_dependency_index(conn):
    conn.executescript(SCHEMA)
    if conn.execute("SELECT 1 FROM research_dependency_index_meta WHERE version=2").fetchone():
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM research_dependency_edges")
        for row in conn.execute("SELECT payload_json FROM research_plan_versions "
                                "ORDER BY plan_id,version").fetchall():
            index_plan(conn, json.loads(row["payload_json"]))
        for row in conn.execute("SELECT payload_json FROM research_snapshots "
                                "ORDER BY project_id,snapshot_version").fetchall():
            index_snapshot(conn, json.loads(row["payload_json"]))
        conn.execute("DELETE FROM research_dependency_index_meta")
        conn.execute("INSERT INTO research_dependency_index_meta(version) VALUES(2)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def affected_targets(conn, project_id, source_kind, source_id, source_version=None):
    return [dict(row) for row in conn.execute(
        "SELECT DISTINCT target_kind,target_id,target_version,source_version "
        "FROM research_dependency_edges "
        "WHERE project_id=? AND source_kind=? AND source_id=? "
        "AND (? IS NULL OR source_version=?) "
        "ORDER BY target_kind,target_id,target_version,source_version",
        (project_id, source_kind, source_id, source_version, source_version),
    )]
