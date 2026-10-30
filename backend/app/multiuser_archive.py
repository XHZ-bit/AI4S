"""Stopped-service backups of identity, every private SQLite DB, and raw files."""

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.data_archive import (
    _CHUNK, _checked_path, _copy_file, _inside_directory, _integrity_check,
    _safe_name, _publish_directory,
)
from app.storage_lock import LOCK_DIRECTORY, storage_maintenance

FORMAT = "research-atlas-multiuser-backup-v1"
_USER_ID = re.compile(r"[a-f0-9]{32}")
_HASH = re.compile(r"[a-f0-9]{64}")
_SIDECARS = {"identity.db-wal", "identity.db-shm", "identity.db-journal"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def _publish_archive(source: Path, target: Path) -> None:
    if os.name == "nt":
        source.rename(target)  # Windows rename refuses an existing destination.
    else:
        # The stage is in target.parent, so both files are on the same device.
        # Unix rename could overwrite a file created after our last check.
        os.link(source, target)


def _portable_name(name: str) -> bool:
    return (isinstance(name, str) and _safe_name(name) and all(
        part.rstrip(". ") == part and part.split(".")[0].upper() not in _RESERVED
        and not any(ord(char) < 32 or char in '<>"|?*' for char in part)
        for part in PurePosixPath(name).parts))


def _account_ids(database: Path) -> list[str]:
    _integrity_check(database)
    with closing(sqlite3.connect(database)) as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM users")]
        # Require the identity schema, including sessions for restore revocation.
        conn.execute("SELECT token_hash,user_id FROM sessions LIMIT 0")
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Identity database contains invalid account references")
    if any(not isinstance(uid, str) or not _USER_ID.fullmatch(uid) for uid in ids):
        raise ValueError("Identity database contains invalid account IDs")
    return sorted(ids)


def _inventory(root: Path) -> tuple[list[Path], list[str], list[str]]:
    identity = root / "identity.db"
    _checked_path(identity, must_exist=True)
    if not identity.is_file():
        raise ValueError("Multiuser backup requires identity.db")
    ids = _account_ids(identity)
    paths = [identity]
    databases = ["identity.db"]
    workspaces = []
    for entry in sorted(root.iterdir()):
        _checked_path(entry, must_exist=True)
        if entry.name in {"identity.db", LOCK_DIRECTORY, *_SIDECARS}:
            continue
        if entry.name == ".model-key" and entry.is_file():
            paths.append(entry)
            continue
        if entry.name != "users" or not entry.is_dir():
            raise ValueError(f"Unexpected multiuser data entry: {entry.name}")
        for user in sorted(entry.iterdir()):
            _checked_path(user, must_exist=True)
            if user.name not in ids or not user.is_dir():
                raise ValueError("Personal workspace has no matching account")
            database = user / "atlas.db"
            if not database.is_file():
                raise ValueError("Personal workspace must contain atlas.db")
            workspaces.append(user.name)
            databases.append(f"users/{user.name}/atlas.db")

            def visit(directory):
                for path in sorted(directory.iterdir()):
                    _checked_path(path, must_exist=True)
                    mode = path.lstat().st_mode
                    if stat.S_ISDIR(mode):
                        visit(path)
                    elif not stat.S_ISREG(mode):
                        raise ValueError("Unsupported personal workspace file")
                    elif not (path.parent == user and path.name in {
                            "atlas.db-wal", "atlas.db-shm", "atlas.db-journal"}):
                        paths.append(path)

            visit(user)
    if any(not _portable_name(path.relative_to(root).as_posix()) for path in paths):
        raise ValueError("Data includes a non-portable archive path")
    return sorted(paths), databases, workspaces


def create_site_backup(data_dir: Path, output: Path) -> dict:
    root = _checked_path(data_dir, must_exist=True)
    output = _checked_path(output)
    if _inside_directory(output, root):
        raise ValueError("Backup archive must be outside the data directory")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with storage_maintenance(root), tempfile.TemporaryDirectory(
            prefix="atlas-site-backup-", dir=output.parent) as folder:
        stage = Path(folder)
        paths, databases, workspaces = _inventory(root)
        # Snapshot every SQLite DB with SQLite's API, including committed WAL data.
        for name in databases:
            snapshot = stage.joinpath(*PurePosixPath(name).parts)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(root / name)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            _integrity_check(snapshot)
        archive_path = stage / "backup.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True) as archive:
            entries = []
            for path in paths:
                name = path.relative_to(root).as_posix()
                entries.append(_copy_file(archive, stage / name if name in databases else path, name))
            if _inventory(root) != (paths, databases, workspaces):
                raise ValueError("Data file inventory changed during backup")
            manifest = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                        "account_ids": _account_ids(stage / "identity.db"),
                        "workspace_ids": workspaces, "databases": databases, "files": entries}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        verify_site_backup(archive_path)
        if output.exists():
            raise FileExistsError(output)
        _publish_archive(archive_path, output)
    return manifest


def _manifest(archive: zipfile.ZipFile) -> dict:
    names = archive.namelist()
    if (len(names) > 100001 or len(names) != len(set(names)) or "manifest.json" not in names
            or archive.getinfo("manifest.json").file_size > 4 * 1024 * 1024):
        raise ValueError("Invalid backup manifest or file inventory")
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise ValueError("Unsupported multiuser backup format")
    if not isinstance(manifest.get("created_at"), str):
        raise ValueError("Invalid backup creation time")
    datetime.fromisoformat(manifest["created_at"])
    entries = manifest.get("files")
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Invalid backup file inventory")
    paths = [entry.get("path") for entry in entries]
    if any(not _portable_name(name) or name == "manifest.json" for name in paths):
        raise ValueError("Unsafe backup path")
    if (len(paths) != len({name.casefold() for name in paths})
            or set(names) != set(paths) | {"manifest.json"}):
        raise ValueError("Invalid backup file inventory")
    for key in ("account_ids", "workspace_ids"):
        value = manifest.get(key)
        if (not isinstance(value, list) or any(not isinstance(uid, str) or not _USER_ID.fullmatch(uid) for uid in value)
                or len(value) != len(set(value))):
            raise ValueError("Invalid backup account inventory")
    workspaces = set(manifest["workspace_ids"])
    if not workspaces <= set(manifest["account_ids"]):
        raise ValueError("Personal workspace has no matching account")
    databases = {"identity.db", *(f"users/{uid}/atlas.db" for uid in workspaces)}
    if (not isinstance(manifest.get("databases"), list)
            or any(not isinstance(name, str) for name in manifest["databases"])
            or len(manifest["databases"]) != len(databases)
            or set(manifest["databases"]) != databases or not databases <= set(paths)):
        raise ValueError("Invalid backup database inventory")
    for name in paths:
        parts = PurePosixPath(name).parts
        if name not in {"identity.db", ".model-key"} and (len(parts) < 3 or parts[0] != "users" or parts[1] not in workspaces):
            raise ValueError("Invalid personal workspace path")
        if parts[-1] in _SIDECARS | {"atlas.db-wal", "atlas.db-shm", "atlas.db-journal"}:
            raise ValueError("SQLite sidecars must not be restored")
    total = 0
    for entry in entries:
        size = entry.get("size")
        if (type(size) is not int or not 0 <= size <= 8 * 1024**3
                or not isinstance(entry.get("sha256"), str) or not _HASH.fullmatch(entry["sha256"])
                or archive.getinfo(entry["path"]).file_size != size
                or stat.S_ISLNK(archive.getinfo(entry["path"]).external_attr >> 16)):
            raise ValueError("Invalid backup file metadata")
        total += size
    if total > 64 * 1024**3:
        raise ValueError("Backup exceeds the supported size limit")
    return manifest


def _extract(archive: zipfile.ZipFile, manifest: dict, stage: Path) -> None:
    for entry in manifest["files"]:
        destination = stage.joinpath(*PurePosixPath(entry["path"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with archive.open(entry["path"]) as reader, destination.open("xb") as writer:
            while chunk := reader.read(_CHUNK):
                size += len(chunk)
                if size > entry["size"]:
                    raise ValueError("Backup size mismatch")
                writer.write(chunk)
                digest.update(chunk)
        if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"Backup checksum mismatch: {entry['path']}")
    for name in manifest["databases"]:
        _integrity_check(stage / name)
    if _account_ids(stage / "identity.db") != sorted(manifest["account_ids"]):
        raise ValueError("Identity database does not match account inventory")


def verify_site_backup(archive_path: Path) -> dict:
    with zipfile.ZipFile(_checked_path(archive_path, must_exist=True)) as archive:
        manifest = _manifest(archive)
        with tempfile.TemporaryDirectory(prefix="atlas-site-verify-", dir=archive_path.absolute().parent) as folder:
            _extract(archive, manifest, Path(folder))
    return manifest


def restore_site_backup(archive_path: Path, target_dir: Path) -> dict:
    target = _checked_path(target_dir)
    if target.exists():
        raise FileExistsError("Restore target must not exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlas-site-restore-", dir=target.parent) as folder:
        stage = Path(folder) / "data"
        stage.mkdir()
        # Validate and extract the same opened archive to avoid a verify/reopen race.
        with zipfile.ZipFile(_checked_path(archive_path, must_exist=True)) as archive:
            manifest = _manifest(archive)
            _extract(archive, manifest, stage)
        with closing(sqlite3.connect(stage / "identity.db")) as conn:
            conn.execute("DELETE FROM sessions")
            # Restoring an older snapshot must not resurrect already consumed
            # password-reset or email-verification links. Older identity schemas
            # predate these additions and remain valid restore inputs.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_tokens'").fetchone():
                conn.execute("DELETE FROM account_tokens")
            if "pending_email" in {row[1] for row in conn.execute("PRAGMA table_info(users)")}:
                conn.execute("UPDATE users SET pending_email=NULL")
            conn.commit()
        _integrity_check(stage / "identity.db")
        if target.exists():
            raise FileExistsError("Restore target appeared while restoring")
        _publish_directory(stage, target)
    return manifest
