from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .client import verify_config
from .config import get_config
from .scheduler import run_daily, run_snapshot, send_pending, status


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须是 YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="V8 维修系统快照同步工具")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="生成本地快照")
    snapshot.add_argument("--date", type=_date, default=date.today())
    snapshot.add_argument("--dry-run", action="store_true")

    daily = sub.add_parser("daily", help="按业务日期生成快照并加入上传 outbox")
    daily.add_argument("--date", type=_date, default=date.today())
    daily.add_argument("--dry-run", action="store_true")

    pending = sub.add_parser("send-pending", help="发送待上传快照并按 outbox 规则重试")
    pending.add_argument("--limit", type=int, default=20)

    stat = sub.add_parser("status", help="查看本地快照和 outbox 状态")
    stat.add_argument("--limit", type=int, default=20)

    sub.add_parser("verify-config", help="检查快照上传配置")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            result = run_snapshot(args.date, dry_run=args.dry_run)
        elif args.command == "daily":
            result = run_daily(args.date, dry_run=args.dry_run)
        elif args.command == "send-pending":
            result = send_pending(args.limit)
        elif args.command == "status":
            result = status(args.limit)
        else:
            result = verify_config(get_config())
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.command == "verify-config" and result.get("enabled") and not result.get("upload_ready"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
