"""Immutable baselines for comparing deterministic project source checks."""

import json
from uuid import uuid4

from app.db import projects as store
from app.research.audit import project_audit


def latest_checkpoint(conn, project_id: str):
    if store.get_project(conn, project_id) is None:
        raise store.NotFoundError("项目不存在")
    row = conn.execute(
        "SELECT checkpoint_id,project_id,input_fingerprint,created_at "
        "FROM research_impact_checkpoints WHERE project_id=? "
        "ORDER BY created_at DESC,rowid DESC LIMIT 1", (project_id,),
    ).fetchone()
    return dict(row) if row else None


def save_checkpoint(conn, project_id: str, expected_fingerprint: str):
    conn.execute("BEGIN IMMEDIATE")
    try:
        report = project_audit(conn, project_id)
        if report["input_fingerprint"] != expected_fingerprint:
            raise store.VersionConflictError("核查输入已变化，请刷新后重试")
        row = conn.execute(
            "SELECT checkpoint_id,project_id,input_fingerprint,created_at "
            "FROM research_impact_checkpoints WHERE project_id=? AND input_fingerprint=?",
            (project_id, expected_fingerprint),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO research_impact_checkpoints "
                "(checkpoint_id,project_id,input_fingerprint,report_json) VALUES(?,?,?,?)",
                (f"impact-{uuid4().hex}", project_id, expected_fingerprint,
                 json.dumps(report, ensure_ascii=False, sort_keys=True)),
            )
            row = conn.execute(
                "SELECT checkpoint_id,project_id,input_fingerprint,created_at "
                "FROM research_impact_checkpoints WHERE project_id=? AND input_fingerprint=?",
                (project_id, expected_fingerprint),
            ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise


def compare_checkpoint(conn, project_id: str, checkpoint_id: str):
    current = project_audit(conn, project_id)
    row = conn.execute(
        "SELECT report_json,created_at FROM research_impact_checkpoints "
        "WHERE project_id=? AND checkpoint_id=?", (project_id, checkpoint_id),
    ).fetchone()
    if row is None:
        raise store.NotFoundError("核查基线不存在")
    baseline = json.loads(row["report_json"])
    before = {issue["id"]: issue for issue in baseline["issues"]}
    after = {issue["id"]: issue for issue in current["issues"]}
    added = [after[key] for key in sorted(after.keys() - before.keys())]
    resolved = [before[key] for key in sorted(before.keys() - after.keys())]
    changed = [{"before": before[key], "after": after[key]}
               for key in sorted(before.keys() & after.keys()) if before[key] != after[key]]
    return {
        "contract_version": "project-impact-changes-v1",
        "project_id": project_id,
        "checkpoint_id": checkpoint_id,
        "baseline_created_at": row["created_at"],
        "baseline_fingerprint": baseline["input_fingerprint"],
        "current_fingerprint": current["input_fingerprint"],
        "added": added, "resolved": resolved, "changed": changed,
        "notice": "仅对比自动核查问题；基线不会修改事实、快照或人工审核状态。",
    }
