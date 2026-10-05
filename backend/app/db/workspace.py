"""Versioned evidence and persistent learning workspaces (additive migrations)."""

import hashlib
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS case_sessions (
 id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_version TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 0, state_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS case_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, digest TEXT NOT NULL,
 bundle_json TEXT NOT NULL, report_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(session_id,digest));

CREATE TABLE IF NOT EXISTS protocols (paper_uid TEXT PRIMARY KEY,data_json TEXT NOT NULL,updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS guide_chunks (passage_id TEXT NOT NULL, profile_hash TEXT NOT NULL, result_json TEXT NOT NULL, PRIMARY KEY(passage_id,profile_hash));
CREATE TABLE IF NOT EXISTS guides (
 paper_uid TEXT PRIMARY KEY, document_id TEXT NOT NULL, result_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, paper_uid TEXT NOT NULL, content_hash TEXT NOT NULL,
 coverage TEXT NOT NULL, filename TEXT, warnings_json TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(paper_uid,content_hash));
CREATE TABLE IF NOT EXISTS passages (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL, heading TEXT NOT NULL,
 text TEXT NOT NULL, page INTEGER, ordinal INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'text');
CREATE TABLE IF NOT EXISTS knowledge (
 id INTEGER PRIMARY KEY, paper_uid TEXT NOT NULL, document_id TEXT,
 passage_id TEXT, quote TEXT NOT NULL DEFAULT '', start_offset INTEGER, end_offset INTEGER,
 layer TEXT NOT NULL DEFAULT 'author_claim', status TEXT NOT NULL DEFAULT 'candidate',
 checks_json TEXT NOT NULL DEFAULT '{}', extraction_version TEXT NOT NULL DEFAULT 'evidence-v1',
 updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, knowledge_id INTEGER NOT NULL,
 action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS extraction_cache (
 passage_id TEXT NOT NULL, version TEXT NOT NULL, completed_at TEXT DEFAULT (datetime('now')),
 PRIMARY KEY(passage_id,version));
CREATE TABLE IF NOT EXISTS workspaces (
 paper_uid TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 1,
 state_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT, paper_uid TEXT NOT NULL, kind TEXT NOT NULL,
 detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS pipeline_stages (
 paper_uid TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, updated_at TEXT DEFAULT (datetime('now')), PRIMARY KEY(paper_uid,stage));
CREATE TABLE IF NOT EXISTS evaluation_labels (
 id INTEGER PRIMARY KEY AUTOINCREMENT, sample_key TEXT NOT NULL UNIQUE,
 split TEXT NOT NULL, relation_type TEXT NOT NULL, expected INTEGER NOT NULL,
 predicted INTEGER NOT NULL, evidence_supported INTEGER NOT NULL,
 annotator TEXT NOT NULL, source TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '');
"""


def init_workspace(conn):
    conn.executescript(SCHEMA)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(passages)")}
    if "metadata_json" not in columns:
        conn.execute(
            "ALTER TABLE passages ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
        )
    # Old approved triples are not retroactively verified.
    conn.execute(
        "INSERT OR IGNORE INTO knowledge(id,paper_uid,status) SELECT id,paper_uid,'legacy_unverified' FROM extraction_proposals"
    )


def stage(conn, uid, name, status, error=None):
    conn.execute(
        "INSERT INTO pipeline_stages(paper_uid,stage,status,error) VALUES(?,?,?,?) ON CONFLICT(paper_uid,stage) DO UPDATE SET status=excluded.status,error=excluded.error,updated_at=datetime('now')",
        (uid, name, status, error),
    )
    conn.commit()


def save_document(conn, uid, parsed, content_hash=None, filename=None):
    sections = [
        s.model_dump() if hasattr(s, "model_dump") else s for s in parsed.sections
    ]
    content_hash = (
        content_hash
        or hashlib.sha256(
            json.dumps(
                [parsed.title, parsed.abstract, sections], ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    did = hashlib.sha256(f"{uid}:{content_hash}".encode()).hexdigest()[:32]
    coverage = "fulltext" if sections else "abstract"
    warnings = ["公式、图片及实验表格尚未自动核验；章节文本不代表完整解析覆盖。"]
    if not sections:
        warnings.append("仅摘要级资料，不提供完整实验指南或强先修结论。")
    conn.execute(
        "INSERT OR IGNORE INTO documents(id,paper_uid,content_hash,coverage,filename,warnings_json) VALUES(?,?,?,?,?,?)",
        (
            did,
            uid,
            content_hash,
            coverage,
            filename,
            json.dumps(warnings, ensure_ascii=False),
        ),
    )
    ordinal = 0
    for sec in (
        [{"heading": "摘要", "text": parsed.abstract, "page": None}]
        if parsed.abstract
        else []
    ) + sections:
        text = sec["text"]
        # Bounded chunks with overlap; original text is preserved exactly for offsets.
        table = sec.get("kind") == "table"
        for start in [0] if table else range(0, len(text), 3600):
            chunk = text if table else text[start : start + 4000]
            if not chunk.strip():
                continue
            pid = f"{did}-{ordinal}"
            conn.execute(
                "INSERT OR IGNORE INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
                (pid, did, sec["heading"], chunk, sec.get("page"), ordinal),
            )
            conn.execute(
                "UPDATE passages SET kind=?,metadata_json=? WHERE id=?",
                (
                    sec.get("kind", "text"),
                    json.dumps(sec.get("metadata", {}), ensure_ascii=False),
                    pid,
                ),
            )
            ordinal += 1
    conn.commit()
    return did


def document_view(conn, uid):
    docs = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM documents WHERE paper_uid=? ORDER BY created_at DESC,rowid DESC",
            (uid,),
        )
    ]
    for doc in docs:
        doc["warnings"] = json.loads(doc.pop("warnings_json"))
        doc["passages"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM passages WHERE document_id=? ORDER BY ordinal",
                (doc["id"],),
            )
        ]
    return docs


def default_state():
    return {
        "reading": {},
        "answers": {},
        "experiments": [],
        "questions": [],
        "profile": {
            "weekly_hours": 10,
            "compute": "未填写",
            "math": "未填写",
            "coding": "未填写",
            "interests": "",
        },
    }


def get_state(conn, uid):
    row = conn.execute("SELECT * FROM workspaces WHERE paper_uid=?", (uid,)).fetchone()
    return (
        {
            "version": row["version"],
            "state": {**default_state(), **json.loads(row["state_json"])},
        }
        if row
        else {"version": 0, "state": default_state()}
    )


def put_state(conn, uid, state, version):
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = get_state(conn, uid)
        if current["version"] != version:
            raise ValueError("工作区已更新，请刷新后重试")
        conn.execute(
            "INSERT INTO workspaces(paper_uid,version,state_json) VALUES(?,?,?) ON CONFLICT(paper_uid) DO UPDATE SET version=excluded.version,state_json=excluded.state_json,updated_at=datetime('now')",
            (uid, version + 1, json.dumps(state, ensure_ascii=False)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get_state(conn, uid)
