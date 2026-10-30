"""Verified local backups of the SQLite database and adjacent user files."""

import hashlib
import gc
import json
import os
import sqlite3
import stat
import tempfile
import time
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

FORMAT = "research-atlas-data-backup-v1"
_DATABASE = "atlas.db"
_SIDECARS = {"atlas.db-wal", "atlas.db-shm", "atlas.db-journal"}
_CHUNK = 1024 * 1024


def _is_link(entry: os.stat_result) -> bool:
    # Windows directory junctions are reparse points, but are not symlinks.
    return stat.S_ISLNK(entry.st_mode) or bool(
        getattr(entry, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _checked_path(path: Path, *, must_exist: bool = False) -> Path:
    """Check every path component without Windows realpath's handle lookup.

    Restricted Windows users can read and stat a directory even when
    GetFinalPathNameByHandle (used by strict resolve) is denied. Metadata checks
    preserve existence and link boundaries without depending on that lookup.
    Check before and after normalization so a link followed by '..' is rejected.
    """
    absolute = path.absolute()
    normalized = Path(os.path.abspath(absolute))
    candidates = dict.fromkeys((absolute, *absolute.parents, normalized, *normalized.parents))
    for candidate in candidates:
        try:
            entry = candidate.lstat()
        except FileNotFoundError:
            if must_exist and candidate == normalized:
                raise
            continue
        if _is_link(entry):
            raise ValueError(f"Linked paths are not supported in data backups: {candidate}")
    return normalized


def _inside_directory(path: Path, root: Path) -> bool:
    # Compare directory identities as well as spellings: Windows short names
    # can name the same directory through a different, non-linked path.
    identity = root.stat()
    for candidate in (path, *path.parents):
        try:
            if os.path.samestat(identity, candidate.stat()):
                return True
        except FileNotFoundError:
            continue
    return False


def _integrity_check(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise ValueError(f"SQLite integrity check failed: {result}")


def _publish_directory(stage: Path, target: Path) -> None:
    """Finish verified restoration without replacing an existing destination."""
    for attempt in range(6):
        if target.exists():
            raise FileExistsError('Restore target appeared while restoring')
        try:
            stage.rename(target)
            return
        except PermissionError:
            # Windows scanners may briefly retain freshly closed SQLite files.
            # Never retry a different error or delete a competing target.
            if os.name != 'nt' or attempt == 5 or target.exists():
                raise
            gc.collect()
            time.sleep(0.15 * (attempt + 1))


def _data_files(root: Path) -> list[Path]:
    files = []

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            entry = path.lstat()
            if _is_link(entry):
                raise ValueError(f"Linked paths are not supported in data backups: {path}")
            if stat.S_ISDIR(entry.st_mode):
                visit(path)
            elif not stat.S_ISREG(entry.st_mode):
                raise ValueError(f"Unsupported data entry: {path}")
            elif path.parent != root or path.name not in {_DATABASE, *_SIDECARS}:
                files.append(path)

    visit(root)
    return files


def _copy_file(archive: zipfile.ZipFile, source: Path, name: str) -> dict:
    before = source.stat()
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as reader, archive.open(name, "w") as writer:
        while chunk := reader.read(_CHUNK):
            writer.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"Data file changed during backup: {source}")
    return {"path": name, "size": size, "sha256": digest.hexdigest()}


def create_backup(data_dir: Path, output: Path) -> dict:
    root = _checked_path(data_dir, must_exist=True)
    database = root / _DATABASE
    if not database.is_file() or _is_link(database.lstat()):
        raise ValueError("Data directory must contain a regular atlas.db file")
    output = _checked_path(output)
    if _inside_directory(output, root):
        raise ValueError("Backup archive must be outside the data directory")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    before_files = _data_files(root)
    with tempfile.TemporaryDirectory(prefix="atlas-backup-", dir=output.parent) as folder:
        temp_root = Path(folder)
        snapshot = temp_root / _DATABASE
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
        _integrity_check(snapshot)
        archive_path = temp_root / "backup.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED,
                             allowZip64=True) as archive:
            entries = [_copy_file(archive, snapshot, _DATABASE)]
            for path in before_files:
                entries.append(_copy_file(archive, path, path.relative_to(root).as_posix()))
            if _data_files(root) != before_files:
                raise ValueError("Data file list changed during backup")
            manifest = {"format": FORMAT,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "files": entries}
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                          sort_keys=True, indent=2))
        verify_backup(archive_path)
        if output.exists():
            raise FileExistsError(output)
        archive_path.rename(output)
    return manifest


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (bool(path.parts) and str(path) == name and "\\" not in name
            and ":" not in name and not path.is_absolute()
            and all(part not in {"", ".", ".."} for part in path.parts))


def verify_backup(archive_path: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("Backup has missing or duplicate entries")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
            raise ValueError("Unsupported backup format")
        entries = manifest["files"]
        expected = {entry["path"] for entry in entries}
        if (_DATABASE not in expected or len(expected) != len(entries)
                or set(names) != expected | {"manifest.json"}
                or any(not _safe_name(name) or name == "manifest.json" for name in expected)):
            raise ValueError("Backup file inventory is invalid")
        with tempfile.TemporaryDirectory(prefix="atlas-verify-", dir=archive_path.absolute().parent) as folder:
            snapshot = Path(folder) / _DATABASE
            for entry in entries:
                digest = hashlib.sha256()
                size = 0
                name = entry["path"]
                if archive.getinfo(name).file_size != entry.get("size"):
                    raise ValueError(f"Backup size mismatch: {name}")
                with archive.open(name) as reader:
                    if name == _DATABASE:
                        with snapshot.open("wb") as writer:
                            while chunk := reader.read(_CHUNK):
                                writer.write(chunk)
                                digest.update(chunk)
                                size += len(chunk)
                    else:
                        while chunk := reader.read(_CHUNK):
                            digest.update(chunk)
                            size += len(chunk)
                if digest.hexdigest() != entry.get("sha256") or size != entry.get("size"):
                    raise ValueError(f"Backup checksum mismatch: {name}")
            _integrity_check(snapshot)
    return manifest


def restore_backup(archive_path: Path, target_dir: Path) -> dict:
    manifest = verify_backup(archive_path)
    target = _checked_path(target_dir)
    if target.exists():
        raise FileExistsError("Restore target must not exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="atlas-restore-", dir=target.parent) as folder:
        stage = Path(folder) / "data"
        stage.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest["files"]:
                destination = stage.joinpath(*PurePosixPath(entry["path"]).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(entry["path"]) as reader, destination.open("xb") as writer:
                    while chunk := reader.read(_CHUNK):
                        writer.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ValueError(f"Backup changed during restore: {entry['path']}")
        _integrity_check(stage / _DATABASE)
        if target.exists():
            raise FileExistsError("Restore target appeared while restoring")
        _publish_directory(stage, target)
    return manifest
