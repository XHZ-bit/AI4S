"""Provision and recover invited accounts without putting passwords in arguments."""

import argparse
import getpass
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from app import accounts  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.storage_lock import StorageBusyError, data_writer  # noqa: E402


def _password():
    first = getpass.getpass("New password (at least 12 characters): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise accounts.AccountError("两次输入的密码不一致")
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create an invited account (initial administrator by default)")
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=("admin", "user"), default="admin")
    commands.add_parser("list", help="List account metadata without credentials")
    for name in ("reset-password", "enable", "disable"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    try:
        with data_writer(Path(get_settings().data_dir)):
            return _execute(args)
    except (accounts.AccountError, StorageBusyError, EOFError, KeyboardInterrupt) as exc:
        print(str(exc) or "操作已取消", file=sys.stderr)
        return 1


def _execute(args):
    try:
        if args.command == "create":
            result = accounts.create_user(args.username, _password(), args.role)
        elif args.command == "list":
            result = {"items": accounts.list_users()}
        else:
            username = args.username.strip().casefold()
            user = next((user for user in accounts.list_users() if user["username"].casefold() == username), None)
            if not user:
                raise accounts.AccountError("账号不存在", 404)
            if args.command == "reset-password":
                accounts.reset_password(user["id"], _password())
                result = {"ok": True, "username": user["username"], "sessions_revoked": True}
            else:
                result = accounts.set_disabled(user["id"], args.command == "disable")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (accounts.AccountError, EOFError, KeyboardInterrupt) as exc:
        print(str(exc) or "操作已取消", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
