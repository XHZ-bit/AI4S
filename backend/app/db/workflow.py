"""Additive storage for explicit mastery and frozen project-step execution."""

import json


SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_mastery (
 concept_uid TEXT PRIMARY KEY, confirmed INTEGER NOT NULL DEFAULT 0,
 version INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
 activity_id TEXT, updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS workflow_mastery_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, concept_uid TEXT NOT NULL,
 version INTEGER NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL,
 activity_id TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
 UNIQUE(concept_uid,version));
CREATE TABLE IF NOT EXISTS workflow_step_records (
 snapshot_id TEXT NOT NULL, step_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
 done INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL DEFAULT '',
 updated_at TEXT NOT NULL DEFAULT (datetime('now')),
 PRIMARY KEY(snapshot_id,step_id));
CREATE TABLE IF NOT EXISTS workflow_step_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id TEXT NOT NULL, step_id TEXT NOT NULL,
 version INTEGER NOT NULL, done INTEGER NOT NULL, outcome TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 UNIQUE(snapshot_id,step_id,version));
CREATE TABLE IF NOT EXISTS workflow_roadmap_lineage (
 parent_id INTEGER NOT NULL UNIQUE, child_id INTEGER NOT NULL UNIQUE,
 created_at TEXT NOT NULL DEFAULT (datetime('now')),
 PRIMARY KEY(parent_id,child_id));
"""


def init_workflow(conn):
    conn.executescript(SCHEMA)


def mastery_version(conn, concept_uid):
    row = conn.execute(
        "SELECT version,confirmed,reason,activity_id,updated_at FROM workflow_mastery WHERE concept_uid=?",
        (concept_uid,),
    ).fetchone()
    return ({"concept_uid": concept_uid, **dict(row)} if row else {
        "concept_uid": concept_uid, "version": 0, "confirmed": 0,
        "reason": "", "activity_id": None, "updated_at": None,
    })


def put_mastery(conn, concept_uid, expected_version, action, reason, activity_id):
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = mastery_version(conn, concept_uid)
        if current["version"] != expected_version:
            raise ValueError("掌握记录已更新，请刷新后重试")
        confirmed = int(action == "confirm")
        if current["confirmed"] == confirmed and current["reason"] == reason and current["activity_id"] == activity_id:
            conn.rollback()
            return current
        version = expected_version + 1
        conn.execute(
            "INSERT INTO workflow_mastery(concept_uid,confirmed,version,reason,activity_id) VALUES(?,?,?,?,?) "
            "ON CONFLICT(concept_uid) DO UPDATE SET confirmed=excluded.confirmed,version=excluded.version,"
            "reason=excluded.reason,activity_id=excluded.activity_id,updated_at=datetime('now')",
            (concept_uid, confirmed, version, reason, activity_id),
        )
        conn.execute(
            "INSERT INTO workflow_mastery_events(concept_uid,version,action,reason,activity_id) VALUES(?,?,?,?,?)",
            (concept_uid, version, action, reason, activity_id),
        )
        conn.commit()
        return mastery_version(conn, concept_uid)
    except Exception:
        conn.rollback()
        raise


def step_record(conn, snapshot_id, step_id):
    row = conn.execute(
        "SELECT version,done,outcome,updated_at FROM workflow_step_records WHERE snapshot_id=? AND step_id=?",
        (snapshot_id, step_id),
    ).fetchone()
    return ({"snapshot_id": snapshot_id, "step_id": step_id, **dict(row)} if row else {
        "snapshot_id": snapshot_id, "step_id": step_id, "version": 0,
        "done": 0, "outcome": "", "updated_at": None,
    })


def put_step_record(conn, snapshot_id, step_id, expected_version, done, outcome):
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = step_record(conn, snapshot_id, step_id)
        if current["version"] != expected_version:
            raise ValueError("步骤记录已更新，请刷新后重试")
        if current["done"] == int(done) and current["outcome"] == outcome:
            conn.rollback()
            return current
        version = expected_version + 1
        conn.execute(
            "INSERT INTO workflow_step_records(snapshot_id,step_id,version,done,outcome) VALUES(?,?,?,?,?) "
            "ON CONFLICT(snapshot_id,step_id) DO UPDATE SET version=excluded.version,done=excluded.done,"
            "outcome=excluded.outcome,updated_at=datetime('now')",
            (snapshot_id, step_id, version, int(done), outcome),
        )
        conn.execute(
            "INSERT INTO workflow_step_events(snapshot_id,step_id,version,done,outcome) VALUES(?,?,?,?,?)",
            (snapshot_id, step_id, version, int(done), outcome),
        )
        conn.commit()
        return step_record(conn, snapshot_id, step_id)
    except Exception:
        conn.rollback()
        raise


def latest_snapshots(conn):
    for row in conn.execute(
        "SELECT s.* FROM research_snapshots s WHERE s.snapshot_version=("
        "SELECT MAX(t.snapshot_version) FROM research_snapshots t WHERE t.project_id=s.project_id) "
        "ORDER BY s.created_at DESC"
    ):
        payload = json.loads(row["payload_json"])
        payload["review_status"] = row["review_status"]
        yield payload
