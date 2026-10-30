import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.data_archive import create_backup, restore_backup, verify_backup
from app.db.sqlite import connect


def _database(directory):
    directory.mkdir()
    with sqlite3.connect(directory / "atlas.db") as conn:
        conn.execute("CREATE TABLE saved(value TEXT)")


def _linked_metadata(monkeypatch, linked, kind):
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        entry = original(path, *args, **kwargs)
        if path == linked:
            return SimpleNamespace(
                st_mode=stat.S_IFLNK if kind == "symlink" else entry.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
                if kind == "junction"
                else 0,
            )
        return entry

    monkeypatch.setattr(Path, "lstat", lstat)


def test_backup_and_restore_keep_committed_database_and_original_files(tmp_path):
    data = tmp_path / "source"
    data.mkdir()
    conn = connect(str(data / "atlas.db"))
    conn.execute(
        "INSERT INTO papers(uid,title,abstract) VALUES('paper-1','Before backup','')"
    )
    conn.commit()
    original = data / "pdfs" / "paper-1.pdf"
    original.parent.mkdir()
    original.write_bytes(b"%PDF-1.4\noriginal")
    archive = tmp_path / "archive.zip"
    manifest = create_backup(data, archive)
    assert {entry["path"] for entry in manifest["files"]} == {
        "atlas.db",
        "pdfs/paper-1.pdf",
    }
    assert verify_backup(archive) == manifest

    conn.execute("UPDATE papers SET title='After backup' WHERE uid='paper-1'")
    conn.commit()
    conn.close()
    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    with sqlite3.connect(restored / "atlas.db") as saved:
        assert (
            saved.execute("SELECT title FROM papers WHERE uid='paper-1'").fetchone()[0]
            == "Before backup"
        )
    assert (restored / "pdfs" / "paper-1.pdf").read_bytes() == b"%PDF-1.4\noriginal"
    with pytest.raises(FileExistsError):
        restore_backup(archive, restored)


def test_backup_rejects_in_place_archive_and_changed_file_list(tmp_path, monkeypatch):
    data = tmp_path / "source"
    data.mkdir()
    conn = connect(str(data / "atlas.db"))
    conn.close()
    pdf = data / "paper.pdf"
    pdf.write_bytes(b"%PDF-original")
    with pytest.raises(ValueError, match="outside"):
        create_backup(data, data / "backup.zip")
    from app import data_archive

    original = data_archive._copy_file

    def changed(archive, source, name):
        entry = original(archive, source, name)
        if source == pdf:
            (data / "new.pdf").write_bytes(b"%PDF-new")
        return entry

    monkeypatch.setattr(data_archive, "_copy_file", changed)
    with pytest.raises(ValueError, match="file list changed during backup"):
        create_backup(data, tmp_path / "changed.zip")
    assert not (tmp_path / "changed.zip").exists()


def test_restore_rejects_tampered_archive_without_creating_target(tmp_path):
    data = tmp_path / "source"
    data.mkdir()
    conn = connect(str(data / "atlas.db"))
    conn.close()
    archive = tmp_path / "valid.zip"
    create_backup(data, archive)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            payload = source.read(name)
            if name == "manifest.json":
                manifest = json.loads(payload)
                manifest["files"][0]["sha256"] = "0" * 64
                payload = json.dumps(manifest).encode()
            target.writestr(name, payload)
    restored = tmp_path / "restored"
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_backup(tampered, restored)
    assert not restored.exists()


def test_backup_restore_do_not_require_windows_handle_path_resolution(
    tmp_path, monkeypatch
):
    data = tmp_path / "source"
    _database(data)
    (data / "paper.pdf").write_bytes(b"original")
    archive = tmp_path / "archive.zip"

    def denied_resolve(*args, **kwargs):
        raise PermissionError("GetFinalPathNameByHandle access denied")

    monkeypatch.setattr(Path, "resolve", denied_resolve)
    create_backup(data, archive)
    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    assert (restored / "paper.pdf").read_bytes() == b"original"
    with sqlite3.connect(restored / "atlas.db") as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchone()[0] == "saved"


@pytest.mark.parametrize("kind", ["symlink", "junction"])
@pytest.mark.parametrize("location", ["source_parent", "source_entry", "output_parent"])
def test_backup_rejects_linked_components_without_traversing_them(
    tmp_path, monkeypatch, kind, location
):
    data = tmp_path / "source"
    _database(data)
    output_dir = tmp_path / "archives"
    output_dir.mkdir()
    nested = data / "linked"
    nested.mkdir()
    linked = {
        "source_parent": data,
        "source_entry": nested,
        "output_parent": output_dir,
    }[location]
    _linked_metadata(monkeypatch, linked, kind)
    original = Path.iterdir

    def iterdir(path):
        if path == linked:
            raise AssertionError("linked directory must not be traversed")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    archive = output_dir / "archive.zip"
    with pytest.raises(ValueError, match="Linked paths"):
        create_backup(data, archive)
    assert not archive.exists()


def test_backup_checks_link_components_before_parent_normalization(
    tmp_path, monkeypatch
):
    from app.data_archive import _checked_path

    linked = tmp_path / "linked"
    linked.mkdir()
    _linked_metadata(monkeypatch, linked, "junction")
    with pytest.raises(ValueError, match="Linked paths"):
        _checked_path(linked / ".." / "archive.zip")


def test_backup_rejects_directory_alias_inside_source(tmp_path, monkeypatch):
    from app import data_archive

    data = tmp_path / "source"
    _database(data)
    alias = tmp_path / "source-short-name"
    alias.mkdir()
    alias_identity = alias.stat()
    original = data_archive.os.path.samestat

    def same_identity(first, second):
        # Simulate a Windows short filename alias without needing 8.3 names
        # enabled on the test volume or permission to create a junction.
        return original(first, second) or original(second, alias_identity)

    monkeypatch.setattr(data_archive.os.path, "samestat", same_identity)
    with pytest.raises(ValueError, match="outside"):
        create_backup(data, alias / "archive.zip")
    assert not (alias / "archive.zip").exists()


def test_path_validation_keeps_missing_source_and_access_denied_errors(
    tmp_path, monkeypatch
):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "missing", tmp_path / "missing.zip")
    data = tmp_path / "source"
    _database(data)
    original = Path.lstat

    def denied(path, *args, **kwargs):
        if path == data:
            raise PermissionError("metadata access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(PermissionError, match="metadata access denied"):
        create_backup(data, tmp_path / "denied.zip")
    assert not (tmp_path / "denied.zip").exists()


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_restore_rejects_linked_target_parent(tmp_path, monkeypatch, kind):
    data = tmp_path / "source"
    _database(data)
    archive = tmp_path / "archive.zip"
    create_backup(data, archive)
    linked = tmp_path / "linked"
    linked.mkdir()
    _linked_metadata(monkeypatch, linked, kind)
    with pytest.raises(ValueError, match="Linked paths"):
        restore_backup(archive, linked / "restored")
    assert not (linked / "restored").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows scanner sharing violation")
def test_verified_directory_publish_retries_transient_lock(tmp_path, monkeypatch):
    from app.data_archive import _publish_directory

    stage, target = tmp_path / "stage", tmp_path / "restored"
    stage.mkdir()
    (stage / "saved.txt").write_text("preserved", encoding="utf8")
    original, attempts = Path.rename, []

    def rename(path, destination):
        attempts.append(path)
        if len(attempts) == 1:
            raise PermissionError("transient scanner lock")
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", rename)
    _publish_directory(stage, target)
    assert (
        len(attempts) == 2
        and (target / "saved.txt").read_text(encoding="utf8") == "preserved"
    )


def test_directory_publish_keeps_competing_target(tmp_path):
    from app.data_archive import _publish_directory

    stage, target = tmp_path / "stage", tmp_path / "restored"
    stage.mkdir()
    target.mkdir()
    (target / "existing.txt").write_text("keep", encoding="utf8")
    with pytest.raises(FileExistsError):
        _publish_directory(stage, target)
    assert (
        stage.is_dir()
        and (target / "existing.txt").read_text(encoding="utf8") == "keep"
    )
