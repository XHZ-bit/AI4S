import os
import threading
from contextlib import contextmanager
from pathlib import Path

from app import storage_lock


def test_finishing_writer_can_leave_lease_for_concurrent_maintenance(tmp_path, monkeypatch):
    """Maintenance can open a released lease before its writer deletes it."""
    writer_unlocked = threading.Event()
    maintenance_lease_open = threading.Event()
    writer_finished = threading.Event()
    failures = []
    original_lock = storage_lock._locked_file
    original_unlink = Path.unlink

    @contextmanager
    def coordinated_lock(path):
        name = threading.current_thread().name
        is_lease = path.name.startswith("writer-")
        with original_lock(path):
            if is_lease and name == "lease-maintenance":
                maintenance_lease_open.set()
                if not writer_finished.wait(10):
                    raise RuntimeError("Writer did not finish while maintenance held its old lease")
            yield
        if is_lease and name == "lease-writer":
            writer_unlocked.set()
            if not maintenance_lease_open.wait(10):
                raise RuntimeError("Maintenance did not open the released lease")

    def windows_unlink(path, *args, **kwargs):
        if (os.name != "nt" and threading.current_thread().name == "lease-writer"
                and path.name.startswith("writer-") and maintenance_lease_open.is_set()):
            # POSIX permits deleting an open file; emulate Windows sharing rules.
            raise PermissionError("Lease is open in maintenance")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(storage_lock, "_locked_file", coordinated_lock)
    monkeypatch.setattr(Path, "unlink", windows_unlink)

    def writer():
        try:
            with storage_lock.data_writer(tmp_path):
                pass
        except BaseException as error:
            failures.append(error)
        finally:
            writer_finished.set()

    def maintenance():
        try:
            if not writer_unlocked.wait(10):
                raise RuntimeError("Writer did not release its lease")
            with storage_lock.storage_maintenance(tmp_path):
                pass
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=writer, name="lease-writer"),
               threading.Thread(target=maintenance, name="lease-maintenance")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)
    assert not any(thread.is_alive() for thread in threads)
    assert not failures
    assert list((tmp_path / storage_lock.LOCK_DIRECTORY).glob("writer-*.lock")) == []
