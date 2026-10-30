"""Create, verify or restore a complete multiuser site archive (service stopped)."""

import argparse
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from app.multiuser_archive import create_site_backup, restore_site_backup, verify_site_backup  # noqa: E402
from app.storage_lock import StorageBusyError  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--data-dir", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--target-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            manifest = create_site_backup(args.data_dir, args.output)
        elif args.command == "verify":
            manifest = verify_site_backup(args.archive)
        else:
            manifest = restore_site_backup(args.archive, args.target_dir)
        print(json.dumps({"format": manifest["format"], "created_at": manifest["created_at"],
                          "accounts": len(manifest["account_ids"]),
                          "workspaces": len(manifest["workspace_ids"]),
                          "files": len(manifest["files"]),
                          "sessions_revoked": args.command == "restore"}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, StorageBusyError, sqlite3.DatabaseError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
