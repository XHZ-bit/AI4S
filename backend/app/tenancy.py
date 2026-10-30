"""Request and worker workspace scope; never fall back to the legacy database."""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Lock, RLock

from app.config import get_settings

current_user: ContextVar[dict | None] = ContextVar("atlas_user", default=None)
_lock_guard = Lock()
_workspace_locks = {}


def data_dir() -> Path:
    settings = get_settings()
    root = Path(settings.data_dir).resolve()
    if settings.access_mode == "local" and current_user.get() is None:
        return root
    user = current_user.get()
    if not user or not re.fullmatch(r"[a-f0-9]{32}", user.get("id", "")):
        raise PermissionError("个人空间需要有效的登录账号")
    return root / "users" / user["id"]


@contextmanager
def user_scope(user):
    token = current_user.set(user)
    try:
        yield
    finally:
        current_user.reset(token)


def task_identity(key):
    """Legacy task IDs repeat in different databases; futures must not collide."""
    return (str(data_dir()), key)


@contextmanager
def workspace_write_lock():
    identity = str(data_dir())
    with _lock_guard:
        lock = _workspace_locks.setdefault(identity, RLock())
    with lock:
        yield
