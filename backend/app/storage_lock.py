"""Cooperative process leases for a stopped-service, consistent site backup.

Servers and account CLIs hold writer leases; maintenance holds the entry gate
and refuses live writers. OS locks release after a crash, unlike PID files.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.data_archive import _checked_path

LOCK_DIRECTORY = ".atlas-locks"


class StorageBusyError(RuntimeError):
    pass


@contextmanager
def _locked_file(path: Path):
    _checked_path(path)
    with path.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise StorageBusyError("Data is in use; stop the service and account commands before backup") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _directory(root: Path) -> Path:
    directory = _checked_path(root / LOCK_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def data_writer(root: Path):
    """Register a process before its first write, until every worker has stopped."""
    directory = _directory(root)
    path = directory / f"writer-{uuid4().hex}.lock"
    with _locked_file(directory / "gate.lock"):
        lease = _locked_file(path)
        lease.__enter__()
    try:
        yield
    finally:
        lease.__exit__(None, None, None)
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            # Windows may refuse deletion if maintenance opened the released
            # lease meanwhile. Its unlocked file is safe for maintenance to reap.
            pass


@contextmanager
def storage_maintenance(root: Path):
    """Prevent new writers and reject existing writers; never stop them by force."""
    directory = _directory(root)
    with _locked_file(directory / "gate.lock"):
        for path in directory.iterdir():
            if path.name == "gate.lock":
                continue
            try:
                _checked_path(path, must_exist=True)
                if not path.name.startswith("writer-") or path.suffix != ".lock" or not path.is_file():
                    raise ValueError("Unexpected storage lock entry")
                with _locked_file(path):
                    pass
                path.unlink(missing_ok=True)
            except FileNotFoundError:
                # A writer may finish while its lease is being inspected.
                continue
        yield
