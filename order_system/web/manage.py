from __future__ import annotations

import argparse
import getpass

from .repository import Repository
from .settings import DB_PATH, ensure_directories


def main() -> int:
    parser = argparse.ArgumentParser(description="TWD Web 服务器账号管理")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="创建登录账号")
    create.add_argument("username")
    create.add_argument("--role", choices=["admin", "sales", "finance", "outsource", "production"], default="sales")
    create.add_argument("--password", help="建议省略，由终端安全输入")
    reset = sub.add_parser("reset-password", help="重置账号密码")
    reset.add_argument("username")
    reset.add_argument("--password", help="建议省略，由终端安全输入")
    args = parser.parse_args()

    ensure_directories()
    repo = Repository(DB_PATH)
    repo.initialize()
    if args.command == "create-user":
        password = args.password or getpass.getpass("密码（至少 10 位）: ")
        if not args.password:
            confirmation = getpass.getpass("再次输入密码: ")
            if password != confirmation:
                raise SystemExit("两次密码不一致")
        user_id = repo.create_user(args.username, password, args.role)
        print(f"已创建账号 {args.username}（{args.role}，ID {user_id}）")
    elif args.command == "reset-password":
        password = args.password or getpass.getpass("新密码（至少 10 位）: ")
        if not args.password:
            confirmation = getpass.getpass("再次输入新密码: ")
            if password != confirmation:
                raise SystemExit("两次密码不一致")
        repo.set_password(args.username, password)
        print(f"已重置账号 {args.username} 的密码")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
