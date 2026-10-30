"""Create, verify, or restore a local Research Atlas data archive."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_archive import create_backup, restore_backup, verify_backup  # noqa: E402


def main():
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
    args = parser.parse_args()
    if args.command == "backup":
        report = create_backup(args.data_dir, args.output)
    elif args.command == "verify":
        report = verify_backup(args.archive)
    else:
        report = restore_backup(args.archive, args.target_dir)
    print(json.dumps({"format": report["format"], "file_count": len(report["files"]),
                      "created_at": report["created_at"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
