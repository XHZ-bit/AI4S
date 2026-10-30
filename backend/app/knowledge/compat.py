"""Versioned research-tool compatibility writes joined to canonical mutations.

This module never commits and never reimports records: callers own both the
canonical write and this compatibility version in the same SQLite transaction.
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException

from app.db import projects
from app.models.research import FieldEvidence, VersionRef
from app.tenancy import current_user


def write_fact_version(conn, before, value, *, actor=None, reason=None, action="edit"):
    meta = value.get("metadata", {})
    fid = meta.get("legacy_fact_id")
    if not fid:
        return
    current = projects.get_fact(conn, fid)
    if current is None or current.project_id != value["project_id"]:
        raise HTTPException(409, "当前图谱记录的研究事实归属已变化，请重新载入")
    if current.version != meta.get("legacy_fact_version"):
        raise HTTPException(409, "研究事实已更新，请重新载入图谱后再修改")
    kind = projects._fact_kind(current)
    changes = {}
    if before.get("label") != value.get("label"):
        changes["metric_name" if kind == "measurement" else "name"] = value["label"]
    # An experiment summary is not its dataset/protocol, and a measurement
    # summary is not its numeric value. Those annotations remain on kw_nodes.
    if kind == "method" and before.get("summary") != value.get("summary"):
        changes["summary"] = value["summary"]
    status = {"human_verified": "user_confirmed", "legacy_unverified": "candidate"}.get(
        value.get("quality_status"), value.get("quality_status", current.status.value)
    )
    if status not in {"candidate", "user_confirmed", "disputed", "withdrawn"}:
        status = current.status.value
    if changes and current.status.value == "withdrawn" and action != "restore":
        raise HTTPException(409, "请先恢复已撤回研究事实，再修订内容")
    if not changes and status == current.status.value:
        return
    user = current_user.get() or {}
    actor = actor or user.get("username") or user.get("id") or "本机用户"
    reason = reason or "在知识图谱中修订当前空间知识"
    timestamp = projects._now()
    payload = current.model_dump(mode="json")
    payload.update(changes)
    payload.update(version=current.version + 1, status=status, updated_at=timestamp)
    if changes:
        payload["source_kind"] = "user_input"
        bindings = [
            b
            for b in current.field_evidence
            if projects._content_field(b.field_path) not in changes
        ]
        for field, content in changes.items():
            bindings.append(
                FieldEvidence(
                    field_path=field,
                    source_kind="user_input",
                    finding_status="reported" if content else "unknown",
                    evidence_ids=[],
                    note="图谱人工修订：" + reason,
                )
            )
        payload["field_evidence"] = [b.model_dump(mode="json") for b in bindings]
    updated = type(current).model_validate(payload)
    projects._insert_fact(conn, updated)
    audit_id = conn.execute(
        "INSERT INTO research_fact_audit(project_id,fact_id,from_version,to_version,action,actor,reason,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            current.project_id,
            fid,
            current.version,
            updated.version,
            "graph:" + action,
            actor,
            reason,
            projects._dump(current),
            projects._dump(updated),
            timestamp.isoformat(),
        ),
    ).lastrowid
    projects._mark_snapshots(
        conn,
        [VersionRef(id=fid, version=current.version)],
        [f"图谱中的研究事实 {fid} 已修订，请复核正式方案依据"],
    )
    from app.db.dependencies import refresh_live_plan_edges

    refresh_live_plan_edges(conn, current.project_id)
    encoded = projects._dump(updated)
    meta.update(
        legacy_fact_version=updated.version,
        legacy_status=status,
        legacy_source_kind=updated.source_kind.value,
        legacy_field_evidence=[
            b.model_dump(mode="json") for b in updated.field_evidence
        ],
        legacy_payload_hash=hashlib.sha256(encoded.encode()).hexdigest(),
        legacy_unverified=status != "user_confirmed",
        source_withdrawn=status == "withdrawn",
        legacy_import_revision=2,
    )
    conn.execute(
        "UPDATE kw_legacy_map SET fingerprint=? WHERE scope_id=? AND legacy_table='research_fact' AND legacy_id=?",
        (meta["legacy_payload_hash"], current.project_id, fid),
    )
    # The canonical quality/edit event already records this action. Mark its
    # compatibility audit as accounted for, so migration does not duplicate it.
    conn.execute(
        "INSERT INTO kw_legacy_map VALUES(?,?,?,?,?,?)",
        (
            current.project_id,
            "research_fact_audit",
            str(audit_id),
            value["id"],
            "kw_history",
            meta["legacy_payload_hash"],
        ),
    )
