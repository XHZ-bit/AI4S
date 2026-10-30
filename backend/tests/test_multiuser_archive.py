import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.accounts import _SCHEMA
from app.db.sqlite import connect
from app.multiuser_archive import create_site_backup, restore_site_backup, verify_site_backup
from app.storage_lock import StorageBusyError, data_writer, storage_maintenance

ALICE = "a" * 32
BOB = "b" * 32
NEW_USER = "c" * 32


def _site(root):
    root.mkdir()
    with closing(sqlite3.connect(root / "identity.db")) as conn:
        conn.executescript(_SCHEMA)
        for uid, name in ((ALICE, "alice"), (BOB, "bob"), (NEW_USER, "unused")):
            conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?,0,?)",
                         (uid, name, name, b"salt", b"hash", "user", 1))
        conn.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", ("old-session", ALICE, "csrf", 1, 9999999999))
        conn.commit()
    for uid, title in ((ALICE, "Private Alice"), (BOB, "Private Bob")):
        user = root / "users" / uid
        raw = b"%PDF-" + title.encode()
        digest = hashlib.sha256(raw).hexdigest()
        with closing(connect(str(user / "atlas.db"))) as conn:
            conn.execute("INSERT INTO papers(uid,title) VALUES('same-paper',?)", (title,))
            conn.execute("INSERT INTO paper_library VALUES('same-paper',?,?,?)",
                         (int(uid == ALICE), int(uid == BOB), "2026-10-19T00:00:00+00:00"))
            conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) "
                         "VALUES('same-document','same-paper',?,'fulltext')", (digest,))
            conn.execute("INSERT INTO paper_reading_positions "
                         "(paper_uid,document_id,content_hash,page,page_count,updated_at) "
                         "VALUES('same-paper','same-document',?,?,4,'2026-10-19T00:00:00+00:00')",
                         (digest, 3 if uid == ALICE else 1))
            conn.commit()
        (user / "pdfs").mkdir()
        (user / "pdfs" / "same-paper.pdf").write_bytes(raw)


def _rewrite(source, target, transform):
    with zipfile.ZipFile(source) as reader, zipfile.ZipFile(target, "w") as writer:
        files = {name: reader.read(name) for name in reader.namelist()}
        manifest = json.loads(files.pop("manifest.json"))
        transform(files, manifest)
        for name, payload in files.items():
            writer.writestr(name, payload)
        writer.writestr("manifest.json", json.dumps(manifest))


def test_site_roundtrip_retains_all_private_data_and_revokes_sessions(tmp_path):
    root = tmp_path / "site"
    _site(root)
    archive = tmp_path / "site.zip"
    manifest = create_site_backup(root, archive)
    assert verify_site_backup(archive) == manifest
    assert manifest["account_ids"] == [ALICE, BOB, NEW_USER]
    assert manifest["workspace_ids"] == [ALICE, BOB]
    assert len(manifest["databases"]) == 3
    assert not any(".atlas-locks" in entry["path"] for entry in manifest["files"])
    target = tmp_path / "restored"
    restore_site_backup(archive, target)
    with closing(sqlite3.connect(target / "identity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    for uid, title in ((ALICE, "Private Alice"), (BOB, "Private Bob")):
        with closing(sqlite3.connect(target / "users" / uid / "atlas.db")) as conn:
            assert conn.execute("SELECT title FROM papers").fetchone()[0] == title
            assert conn.execute("SELECT starred,read_later FROM paper_library").fetchone() == (
                int(uid == ALICE), int(uid == BOB))
            assert conn.execute("SELECT paper_uid,document_id,page,page_count,content_hash,updated_at "
                                "FROM paper_reading_positions").fetchone() == (
                "same-paper", "same-document", 3 if uid == ALICE else 1, 4,
                hashlib.sha256(b"%PDF-" + title.encode()).hexdigest(), "2026-10-19T00:00:00+00:00")
        assert (target / "users" / uid / "pdfs" / "same-paper.pdf").read_bytes() == b"%PDF-" + title.encode()
    with pytest.raises(FileExistsError):
        restore_site_backup(archive, target)


def test_backup_includes_committed_wal_without_sidecars(tmp_path):
    root = tmp_path / "site"
    _site(root)
    with closing(sqlite3.connect(root / "users" / ALICE / "atlas.db")) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("UPDATE papers SET title='Committed WAL'")
        conn.commit()
        archive = tmp_path / "site.zip"
        manifest = create_site_backup(root, archive)
        assert not any(entry["path"].endswith(("-wal", "-shm")) for entry in manifest["files"])
    restored = tmp_path / "restored"
    restore_site_backup(archive, restored)
    with closing(sqlite3.connect(restored / "users" / ALICE / "atlas.db")) as conn:
        assert conn.execute("SELECT title FROM papers").fetchone()[0] == "Committed WAL"


@pytest.mark.parametrize("email_schema", [False, True], ids=["legacy-identity", "email-identity"])
def test_restore_discards_short_lived_credentials_but_retains_recovery_codes(tmp_path, email_schema):
    root = tmp_path / "site"
    _site(root)
    with closing(sqlite3.connect(root / "identity.db")) as conn:
        conn.execute("INSERT INTO recovery_codes VALUES(?,?)", (ALICE, "saved-recovery-code-hash"))
        if email_schema:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.execute("ALTER TABLE users ADD COLUMN pending_email TEXT")
            conn.execute("UPDATE users SET email=?,pending_email=? WHERE id=?",
                         ("alice@example.com", "new@example.com", ALICE))
            conn.executemany("INSERT INTO account_tokens VALUES(?,?,?,?,?,?)", [
                ("reset-hash", ALICE, "reset-password", "alice@example.com", 1, 9999999999),
                ("verify-hash", ALICE, "verify-email", "new@example.com", 1, 9999999999),
            ])
        else:
            conn.execute("DROP TABLE account_tokens")
        conn.commit()
    archive = tmp_path / "site.zip"
    create_site_backup(root, archive)
    restored = tmp_path / "restored"
    restore_site_backup(archive, restored)
    with closing(sqlite3.connect(restored / "identity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT user_id,code_hash FROM recovery_codes").fetchall() == [
            (ALICE, "saved-recovery-code-hash")]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if email_schema:
            assert conn.execute("SELECT COUNT(*) FROM account_tokens").fetchone()[0] == 0
            assert conn.execute("SELECT email,pending_email FROM users WHERE id=?", (ALICE,)).fetchone() == (
                "alice@example.com", None)
        else:
            assert "pending_email" not in columns
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='account_tokens'").fetchone() is None
    # Revocation changes only the restored copy; it never mutates the source.
    with closing(sqlite3.connect(root / "identity.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        if email_schema:
            assert conn.execute("SELECT COUNT(*) FROM account_tokens").fetchone()[0] == 2
            assert conn.execute("SELECT pending_email FROM users WHERE id=?", (ALICE,)).fetchone()[0] == "new@example.com"


def test_live_writer_blocks_backup_even_in_another_process(tmp_path):
    root = tmp_path / "site"
    _site(root)
    with data_writer(root):
        with pytest.raises(StorageBusyError):
            create_site_backup(root, tmp_path / "blocked.zip")
        result = subprocess.run(
            [sys.executable, "scripts/site_archive.py", "backup", "--data-dir", str(root),
             "--output", str(tmp_path / "child.zip")],
            cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 1
        assert "stop the service" in result.stderr
    assert not (tmp_path / "blocked.zip").exists()
    assert not (tmp_path / "child.zip").exists()
    create_site_backup(root, tmp_path / "after-stop.zip")


def test_maintenance_blocks_new_writers_and_reaps_crashed_leases(tmp_path):
    root = tmp_path / "site"
    (root / ".atlas-locks").mkdir(parents=True)
    stale = root / ".atlas-locks" / "writer-crashed.lock"
    stale.write_bytes(b"0")
    with storage_maintenance(root):
        assert not stale.exists()
        with pytest.raises(StorageBusyError):
            with data_writer(root):
                pytest.fail("Maintenance must block new writers")
    with data_writer(root), data_writer(root):
        pass  # Server and operator CLI may coexist during normal operation.


def test_multiuser_lifespan_keeps_lease_through_worker_shutdown(tmp_path, monkeypatch):
    from app import accounts, main
    root = tmp_path / "site"
    _site(root)
    settings = SimpleNamespace(data_dir=str(root), access_mode="multiuser")
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(accounts, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "recover_workspace", lambda: None)
    shutdown = []

    def stop_workers(wait):
        shutdown.append(wait)
        with pytest.raises(StorageBusyError):
            with storage_maintenance(root):
                pytest.fail("Lease released before worker shutdown")

    monkeypatch.setattr(main, "shutdown_executor", stop_workers)

    async def exercise():
        async with main.lifespan(main.app):
            with pytest.raises(StorageBusyError):
                with storage_maintenance(root):
                    pytest.fail("Server should block backup")
        with storage_maintenance(root):
            pass

    asyncio.run(exercise())
    assert shutdown == [True]


@pytest.mark.parametrize("malformation", [
    "hash", "traversal", "case-alias", "orphan", "unknown-file", "sidecar", "timestamp", "database-type",
])
def test_invalid_archives_never_create_restore_target(tmp_path, malformation):
    root = tmp_path / "site"
    _site(root)
    valid = tmp_path / "valid.zip"
    create_site_backup(root, valid)

    def corrupt(files, manifest):
        if malformation == "hash":
            manifest["files"][0]["sha256"] = "0" * 64
        elif malformation in {"traversal", "case-alias", "sidecar"}:
            original = f"users/{ALICE}/pdfs/same-paper.pdf"
            entry = next(entry for entry in manifest["files"] if entry["path"] == original)
            name = {"traversal": "../escape", "case-alias": original.upper(),
                    "sidecar": f"users/{ALICE}/atlas.db-wal"}[malformation]
            if malformation == "case-alias":
                manifest["files"].append({**entry, "path": name})
                files[name] = files[original]
            else:
                entry["path"] = name
                files[name] = files.pop(original)
        elif malformation == "orphan":
            manifest["account_ids"].remove(ALICE)
        elif malformation == "timestamp":
            manifest.pop("created_at")
        elif malformation == "database-type":
            manifest["databases"][0] = {"unsafe": "identity.db"}
        else:
            files["not-in-manifest.txt"] = b"unexpected"

    bad = tmp_path / "bad.zip"
    _rewrite(valid, bad, corrupt)
    target = tmp_path / "restore"
    with pytest.raises(ValueError):
        restore_site_backup(bad, target)
    assert not target.exists()
    assert not (tmp_path / "escape").exists()


def test_backup_refuses_orphan_workspace_and_legacy_mixed_root(tmp_path):
    root = tmp_path / "site"
    _site(root)
    orphan = root / "users" / ("d" * 32)
    orphan.mkdir()
    with pytest.raises(ValueError, match="matching account"):
        create_site_backup(root, tmp_path / "orphan.zip")
    orphan.rmdir()
    (root / "atlas.db").write_bytes(b"legacy local data")
    with pytest.raises(ValueError, match="Unexpected multiuser"):
        create_site_backup(root, tmp_path / "mixed.zip")
    with pytest.raises(ValueError, match="outside"):
        create_site_backup(root, root / "in-place.zip")


def test_backup_preserves_output_created_during_final_publication(tmp_path, monkeypatch):
    from app import multiuser_archive
    root = tmp_path / "site"
    _site(root)
    output = tmp_path / "site.zip"
    publish = multiuser_archive._publish_archive

    def competing_output(source, target):
        target.write_bytes(b"another operator's backup")
        return publish(source, target)

    monkeypatch.setattr(multiuser_archive, "_publish_archive", competing_output)
    with pytest.raises(FileExistsError):
        create_site_backup(root, output)
    assert output.read_bytes() == b"another operator's backup"


def test_backup_rejects_links_before_traversing(tmp_path, monkeypatch):
    from app import data_archive
    import stat
    root = tmp_path / "site"
    _site(root)
    linked = root / "users" / ALICE / "pdfs"
    original = Path.lstat

    def linked_metadata(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return result

    monkeypatch.setattr(data_archive.Path, "lstat", linked_metadata)
    with pytest.raises(ValueError, match="Linked paths"):
        create_site_backup(root, tmp_path / "linked.zip")
