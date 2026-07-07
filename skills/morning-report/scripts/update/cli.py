"""CLI for Morning Report update phases."""

from __future__ import annotations

import argparse
import json

from config_status import DEFAULT_STATE, DEFAULT_USER
from update.apply_confirmed_update import apply_phase
from update.check_current_config import check_config_phase
from update.preview_update import preview
from update.save_confirmed_update import save_phase
from update_config import DEFAULT_AUDIT_LOG


DEFAULT_WORK_DIR = "/tmp/morning-report-update"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Morning Report update phases")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Path to current-topics.md")
    parser.add_argument("--user", default=str(DEFAULT_USER), help="Path to USER.md")
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG), help="Path to audit.log")
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    parser.add_argument("--agent", action="store_true", help="Keep output action-oriented for the agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-config", help="Check current config before previewing an update")

    preview_parser = sub.add_parser("preview", help="Preview an update without writing files")
    preview_parser.add_argument("--replace-topic", action="append", default=[])
    preview_parser.add_argument("--add-topic", action="append", default=[])
    preview_parser.add_argument("--remove-topic", action="append", default=[])
    preview_parser.add_argument("--add-optional-topic", action="append", default=[])
    preview_parser.add_argument("--remove-optional-topic", action="append", default=[])
    preview_parser.add_argument("--reprioritize-topic", action="append", default=[])
    preview_parser.add_argument("--delivery-time")
    preview_parser.add_argument("--timezone")
    preview_parser.add_argument("--report-style")
    preview_parser.add_argument("--report-language")
    preview_parser.add_argument("--audio-summary")
    preview_parser.add_argument("--delivery-channel")
    preview_parser.add_argument("--status")

    apply_parser = sub.add_parser("apply", help="Handle a confirmed update preview")
    apply_parser.add_argument("--preview-file", required=True)

    save_parser = sub.add_parser("save", help="Save a confirmed update preview and verify config")
    save_parser.add_argument("--preview-file", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "check-config":
        result = check_config_phase(args)
    elif args.command == "preview":
        result = preview(args)
    elif args.command == "apply":
        result = apply_phase(args)
    elif args.command == "save":
        result = save_phase(args)
    else:
        parser.error(f"unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if result.get("success") else 2
