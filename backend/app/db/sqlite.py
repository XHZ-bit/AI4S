import json
import sqlite3
from pathlib import Path
from threading import RLock

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    uid TEXT PRIMARY KEY,
    arxiv_id TEXT UNIQUE,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    authors_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    venue TEXT,
    categories_json TEXT NOT NULL DEFAULT '[]',
    published TEXT,
    pdf_url TEXT,
    code_url TEXT,
    source TEXT NOT NULL DEFAULT 'arxiv',
    parse_status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS extraction_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_uid TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    embedding BLOB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS entity_vectors (
    uid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vector BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_embeddings (
    paper_uid TEXT PRIMARY KEY,
    embedding BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS roadmaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_MEMORY_DB = ":memory:"

_initialized_paths: set[str] = set()
_schema_lock = RLock()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    task_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "result_json" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN result_json TEXT")
    from app.db.workspace import init_workspace
    from app.db.projects import init_research_schema

    init_workspace(conn)
    init_research_schema(conn)
    conn.commit()


def connect(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        from app.config import get_settings

        db_path = str(Path(get_settings().data_dir) / "atlas.db")
    # ":memory:" 是特殊值，不存在父目录，跳过 mkdir
    is_memory = db_path == _MEMORY_DB
    if not is_memory:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False 允许连接跨线程复用（如 FastAPI threadpool / 后台任务线程），
    # 底层 SQLite 为 serialized 模式，由连接级锁保证安全
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # 并发写保护：等待锁而不是立刻抛 database is locked（连接级 PRAGMA）
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        with _schema_lock:
            if is_memory or db_path not in _initialized_paths:
                if not is_memory:
                    conn.execute("PRAGMA journal_mode=WAL")
                _init_schema(conn)
                if not is_memory:
                    _initialized_paths.add(db_path)
    except Exception:
        conn.close()
        raise
    return conn


def reset_running_tasks(conn: sqlite3.Connection) -> int:
    """把遗留的 running 任务标记为 failed（服务重启时后台任务已不存在）。"""
    cur = conn.execute(
        "UPDATE tasks SET status='failed', error='interrupted by restart', "
        "updated_at=datetime('now') WHERE status IN ('running','queued')"
    )
    conn.commit()
    return cur.rowcount


def reset_research_running_tasks(conn: sqlite3.Connection) -> int:
    """Interrupt durable research tasks whose local worker vanished on restart."""

    from app.db.projects import interrupt_incomplete_tasks

    interrupted = interrupt_incomplete_tasks(conn)
    conn.execute(
        "UPDATE research_projection_outbox SET status='failed', "
        "last_error='interrupted by restart', updated_at=datetime('now') "
        "WHERE status='running'"
    )
    conn.commit()
    return interrupted


def upsert_paper(conn: sqlite3.Connection, doc: dict) -> str:
    conn.execute(
        """INSERT INTO papers (uid, arxiv_id, title, abstract, authors_json, year, venue,
             categories_json, published, pdf_url, code_url, source)
           VALUES (:uid, :arxiv_id, :title, :abstract, :authors_json, :year, :venue,
             :categories_json, :published, :pdf_url, :code_url, :source)
           ON CONFLICT(uid) DO UPDATE SET
             title=excluded.title, abstract=excluded.abstract,
             authors_json=excluded.authors_json, year=excluded.year, venue=excluded.venue,
             categories_json=excluded.categories_json, published=excluded.published,
             pdf_url=excluded.pdf_url, code_url=excluded.code_url""",
        {
            **doc,
            "authors_json": json.dumps(doc["authors"], ensure_ascii=False),
            "categories_json": json.dumps(doc["categories"], ensure_ascii=False),
        },
    )
    conn.commit()
    return doc["uid"]


def get_paper(conn: sqlite3.Connection, uid: str) -> dict | None:
    row = conn.execute("SELECT * FROM papers WHERE uid = ?", (uid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["authors"] = json.loads(d.pop("authors_json"))
    d["categories"] = json.loads(d.pop("categories_json"))
    return d
