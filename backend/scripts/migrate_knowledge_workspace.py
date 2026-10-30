"""Additively import legacy project sources/records without model calls."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from app.knowledge.migration import migrate_site  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="Explicit existing data root; includes account scopes under users/")
    parser.add_argument("--project-id", help="Import only this project in its owning root/account scope")
    parser.add_argument("--account-id", action="append", help="Limit account scopes to these IDs; repeat to select several accounts")
    parser.add_argument("--root-only", action="store_true", help="Only import the local root atlas.db, never account/test workspaces")
    parser.add_argument("--accounts-only", action="store_true", help="Skip root atlas.db and import only selected/registered account scopes")
    parser.add_argument("--relocate-from", type=Path, help="After copying originals, verify hashes and rebase kw_assets paths from this former data root")
    args = parser.parse_args(argv)
    if args.root_only and (args.accounts_only or args.account_id):
        parser.error("--root-only cannot be combined with account selection")
    try:
        result = migrate_site(args.data_dir, args.project_id, account_ids=set() if args.root_only else set(args.account_id) if args.account_id else None,
                              include_root=not args.accounts_only, relocate_from=args.relocate_from)
    except (ValueError, OSError, sqlite3.DatabaseError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.project_id and not any(scope["projects"] for scope in result["scopes"]):
        print("所选资料目录中没有找到可迁移的活动项目", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
