"""User-saved learning experiences, scoped to an account and research space."""

import json

from fastapi import HTTPException

from app.knowledge import practice, store


def init(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kw_learning_experiences ("
        "project_id TEXT NOT NULL, node_id TEXT NOT NULL, id TEXT NOT NULL, "
        "data TEXT NOT NULL, PRIMARY KEY(project_id,node_id,id))"
    )


def list_entries(conn, project_id, node_id):
    store.record(conn, "kw_nodes", project_id, node_id)
    init(conn)
    rows = conn.execute(
        "SELECT data FROM kw_learning_experiences WHERE project_id=? AND node_id=? "
        "ORDER BY rowid DESC LIMIT 100", (project_id, node_id)
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def save(conn, project_id, node_id, practice_id, content):
    store.record(conn, "kw_nodes", project_id, node_id)
    practice.init(conn)
    artifact = practice.record(conn, project_id, practice_id)
    if artifact["node_id"] != node_id:
        raise HTTPException(404, "练习不属于当前知识节点")
    content = content.strip()
    if not content:
        raise HTTPException(422, "请填写希望保存的经验")
    init(conn)
    entry_id = store.identity("user-ai-feedback-v1", project_id, node_id, practice_id, content)
    entry = {
        "id": entry_id, "node_id": node_id, "practice_id": practice_id,
        "content": content, "origin": "user_saved_ai_feedback", "created_at": store.now(),
    }
    conn.execute(
        "INSERT OR IGNORE INTO kw_learning_experiences(project_id,node_id,id,data) VALUES(?,?,?,?)",
        (project_id, node_id, entry_id, store.encode(entry)),
    )
    row = conn.execute(
        "SELECT data FROM kw_learning_experiences WHERE project_id=? AND node_id=? AND id=?",
        (project_id, node_id, entry_id),
    ).fetchone()
    return json.loads(row[0])
