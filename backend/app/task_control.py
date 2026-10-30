"""Cooperative cancellation and deadlines at safe task boundaries."""

import time
from contextlib import closing, contextmanager
from contextvars import ContextVar
from threading import RLock

_current = ContextVar("atlas_task", default=None)
_futures = {}
_future_lock = RLock()


def track_future(key, future, release):
    if future is None or not hasattr(future, 'add_done_callback'):
        return
    from app.tenancy import task_identity
    key = task_identity(key)
    with _future_lock:
        _futures[key] = future
    def completed(value):
        with _future_lock:
            if _futures.get(key) is value:
                _futures.pop(key, None)
        if value.cancelled():
            release()
    future.add_done_callback(completed)


class TaskStopped(RuntimeError):
    pass


def init_controls(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS task_controls (
      task_key TEXT PRIMARY KEY, cancel_requested INTEGER NOT NULL DEFAULT 0,
      phase TEXT NOT NULL DEFAULT 'queued', progress REAL NOT NULL DEFAULT 0,
      started_at REAL, heartbeat_at REAL, deadline_at REAL, error_code TEXT,
      checkpoints_json TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS idx_tasks_state_updated ON tasks(status,updated_at,id);
    """)


@contextmanager
def task_scope(key):
    token = _current.set(key)
    try:
        yield
    finally:
        _current.reset(token)


def check_active(conn=None):
    key = _current.get()
    if key is None:
        return
    from app.tenancy import current_user
    user = current_user.get()
    if user:
        from app.accounts import is_active
        if not is_active(user['id']):
            raise TaskStopped("账号已停用，任务停止；已保存结果保留")
    if conn is None:
        from app.db.sqlite import connect
        with closing(connect()) as database:
            return check_active(database)
    row = conn.execute("SELECT * FROM task_controls WHERE task_key=?", (key,)).fetchone()
    if row and row["cancel_requested"]:
        raise TaskStopped("任务已取消；已保存阶段结果保留")
    if row and row["deadline_at"] and time.time() > row["deadline_at"]:
        raise TaskStopped("任务超过总时限；可从安全阶段重试")


def checkpoint(conn, phase, progress):
    check_active(conn)
    key = _current.get()
    if key:
        from app.config import get_settings
        now = time.time()
        conn.execute(
            "INSERT INTO task_controls(task_key,phase,progress,started_at,heartbeat_at,deadline_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(task_key) DO UPDATE SET "
            "phase=excluded.phase,progress=excluded.progress,heartbeat_at=excluded.heartbeat_at,"
            "started_at=coalesce(started_at,excluded.started_at),deadline_at=coalesce(deadline_at,excluded.deadline_at)",
            (key, phase, progress, now, now, now + get_settings().task_timeout_seconds),
        )
        conn.commit()


def stop_task(conn, key):
    if key.startswith("legacy:"):
        table, column, ident, terminal = "tasks", "id", int(key.split(":", 1)[1]), "cancelled"
    else:
        table, column, ident, terminal = "research_async_tasks", "task_id", key.split(":", 1)[1], "interrupted"
    row = conn.execute(f"SELECT status FROM {table} WHERE {column}=?", (ident,)).fetchone()
    if row is None:
        raise LookupError("任务不存在")
    if row["status"] not in ("queued", "running", "cancelled", "interrupted"):
        raise ValueError("只能取消排队或运行中的任务")
    conn.execute("INSERT INTO task_controls(task_key,cancel_requested,error_code) VALUES(?,1,'cancelled') "
                 "ON CONFLICT(task_key) DO UPDATE SET cancel_requested=1,error_code='cancelled'", (key,))
    conn.execute(f"UPDATE {table} SET status=?,updated_at=datetime('now') WHERE {column}=? "
                 "AND status IN ('queued','running')", (terminal, ident))
    conn.commit()
    from app.tenancy import task_identity
    with _future_lock:
        future = _futures.get(task_identity(key))
    if future is not None:
        future.cancel()
    return {"task_key": key, "status": terminal, "cancel_requested": True}


def error_code(exc):
    import httpx
    if isinstance(exc, TaskStopped):
        if "停用" in str(exc):
            return "account_disabled"
        return "cancelled" if "取消" in str(exc) else "deadline_exceeded"
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "rate_limited" if exc.response.status_code == 429 else "remote_error"
    if isinstance(exc, httpx.ConnectError):
        return "service_unavailable"
    return "task_failed"
