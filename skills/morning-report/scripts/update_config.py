#!/usr/bin/env python3
"""Update Morning Report runtime state safely.

This helper is used by the agent after user confirmation. It preserves the
canonical current-topics.md shape and can optionally sync USER.md's Morning
Report Preferences section.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_style import normalize_report_style

SKILL_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = SKILL_DIR.parent.parent
DEFAULT_STATE = SKILL_DIR / "state" / "current-topics.md"
DEFAULT_USER = WORKSPACE / "USER.md"
DEFAULT_AUDIT_LOG = SKILL_DIR / "state" / "audit.log"

PREF_KEYS = [
    "Delivery time",
    "Timezone",
    "Report style",
    "Report language",
    "Audio summary",
    "Delivery channel",
]


class ConfigUpdateError(ValueError):
    """Raised when a requested config mutation would produce invalid state."""


def write_audit(path: Path, action: str, details: dict[str, Any]) -> None:
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "by": "update_config.py",
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def _numbered_items(section: str) -> list[str]:
    items = []
    for line in section.splitlines():
        match = re.match(r"^\s*\d+\.\s+(.+?)\s*$", line)
        if match:
            value = match.group(1).strip()
            if value and value.lower() != "none provided.":
                items.append(value)
    return items


def _optional_items(section: str) -> list[str]:
    if not section or "none provided" in section.lower():
        return []
    numbered = _numbered_items(section)
    if numbered:
        return numbered
    items = []
    for line in section.splitlines():
        match = re.match(r"^\s*-\s+(.+?)\s*$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def _bullet_map(section: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"^\s*-\s+([^:]+):\s*(.*?)\s*$", line)
        if match:
            data[match.group(1).strip()] = match.group(2).strip()
    return data


def read_state(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    status_match = re.search(r"^Status:\s*(.+?)\s*$", text, re.MULTILINE)
    prefs = _bullet_map(_section(text, "Report preferences"))
    return {
        "status": status_match.group(1).strip() if status_match else "not_configured",
        "active_topics": _numbered_items(_section(text, "Active topics")),
        "optional_topics": _optional_items(_section(text, "Optional topics")),
        "user_priority": _numbered_items(_section(text, "User priority")),
        "preferences": prefs,
    }


def read_user_prefs(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return _bullet_map(_section(text, "Morning Report Preferences"))


def render_numbered(items: list[str]) -> str:
    return "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, 1)) or "None provided."


def render_optional(items: list[str]) -> str:
    return render_numbered(items) if items else "None provided."


def render_state(data: dict[str, Any]) -> str:
    prefs = data["preferences"]
    active_topics = _dedupe(data.get("active_topics", []))
    optional_topics = _dedupe(data.get("optional_topics", []))
    user_priority = _dedupe(data.get("user_priority") or active_topics)
    lines = [
        "# Current Topics",
        "",
        "## Setup status",
        "",
        f"Status: {data.get('status', 'not_configured')}",
        "",
        "## Active topics",
        "",
        render_numbered(active_topics),
        "",
        "## Optional topics",
        "",
        render_optional(optional_topics),
        "",
        "## User priority",
        "",
        render_numbered(user_priority),
        "",
        "## Report preferences",
        "",
    ]
    for key in PREF_KEYS:
        lines.append(f"- {key}: {prefs.get(key, '')}")
    return "\n".join(lines).rstrip() + "\n"


def render_user_section(status: str, topics: list[str], prefs: dict[str, str]) -> str:
    lines = [
        "## Morning Report Preferences",
        "",
        f"- Status: {status}",
        f"- Topics: {', '.join(topics)}",
    ]
    for key in PREF_KEYS:
        lines.append(f"- {key}: {prefs.get(key, '')}")
    return "\n".join(lines).rstrip() + "\n"


def sync_user(path: Path, status: str, state: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else "# USER.md - About Your Human\n"
    section = render_user_section(status, state["active_topics"], state["preferences"])
    match = re.search(r"^##\s+Morning Report Preferences\s*$", text, re.MULTILINE)
    if not match:
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text.rstrip() + "\n\n" + section + "\n", encoding="utf-8")
        return
    start = match.start()
    next_match = re.search(r"^##\s+", text[match.end():], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(text)
    new_text = text[:start].rstrip() + "\n\n" + section.rstrip() + "\n\n" + text[end:].lstrip()
    path.write_text(new_text, encoding="utf-8")


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_state(state), encoding="utf-8")


def remove_values(existing: list[str], values: list[str]) -> tuple[list[str], list[str]]:
    remove_set = {value.lower().strip() for value in values}
    removed = [item for item in existing if item.lower().strip() in remove_set]
    remaining = [item for item in existing if item.lower().strip() not in remove_set]
    return remaining, removed


def validate_topic_args(args: argparse.Namespace) -> None:
    topics = getattr(args, "topic", None)
    if topics is not None and not _dedupe(topics):
        raise ConfigUpdateError("topic_required: provide at least one non-empty topic")


def require_active_topics(state: dict[str, Any]) -> None:
    if not state.get("active_topics"):
        raise ConfigUpdateError(
            "active_topics_required: Morning Report must have at least one active topic"
        )


def require_runnable_config(state: dict[str, Any]) -> None:
    require_active_topics(state)
    missing = [key for key in PREF_KEYS if not state.get("preferences", {}).get(key)]
    if missing:
        raise ConfigUpdateError("missing_report_preferences: " + ", ".join(missing))
    try:
        state["preferences"]["Report style"] = normalize_report_style(
            state["preferences"]["Report style"]
        )
    except ValueError as exc:
        raise ConfigUpdateError(str(exc)) from exc


def default_user_status_for_state(state_status: str) -> str:
    if state_status == "configured":
        return "enabled"
    return state_status


def apply_command(args: argparse.Namespace, state: dict[str, Any], user_prefs: dict[str, str]) -> tuple[dict[str, Any], str, bool, list[str]]:
    warnings: list[str] = []
    user_status = user_prefs.get("Status") or "preferences_saved_schedule_pending"
    sync = False

    if args.command == "setup":
        state["status"] = args.state_status
        state["active_topics"] = _dedupe(args.topic)
        state["optional_topics"] = _dedupe(args.optional_topic or [])
        state["user_priority"] = _dedupe(args.topic)
        state["preferences"] = {
            "Delivery time": args.delivery_time,
            "Timezone": args.timezone,
            "Report style": args.report_style,
            "Report language": args.report_language,
            "Audio summary": args.audio_summary,
            "Delivery channel": args.delivery_channel,
        }
        require_runnable_config(state)
        user_status = args.user_status
        sync = True
    elif args.command == "replace-topics":
        state["active_topics"] = _dedupe(args.topic)
        if args.optional_topic is not None:
            state["optional_topics"] = _dedupe(args.optional_topic)
        state["user_priority"] = _dedupe(args.topic)
        require_active_topics(state)
        sync = args.sync_user
    elif args.command == "add-topic":
        state["active_topics"] = _dedupe(state["active_topics"] + args.topic)
        state["user_priority"] = _dedupe((state.get("user_priority") or []) + args.topic)
        if not state["user_priority"]:
            state["user_priority"] = list(state["active_topics"])
        require_active_topics(state)
        sync = args.sync_user
    elif args.command == "remove-topic":
        state["active_topics"], removed = remove_values(state["active_topics"], args.topic)
        state["user_priority"], _ = remove_values(state.get("user_priority") or [], args.topic)
        missing = [t for t in args.topic if t.lower().strip() not in {r.lower().strip() for r in removed}]
        if missing:
            warnings.append("topics_not_found: " + ", ".join(missing))
        if removed and not state["active_topics"]:
            raise ConfigUpdateError(
                "cannot_remove_last_active_topic: replace the topic first or disable Morning Report explicitly"
            )
        sync = args.sync_user
    elif args.command == "add-optional-topic":
        state["optional_topics"] = _dedupe(state["optional_topics"] + args.topic)
        sync = args.sync_user
    elif args.command == "remove-optional-topic":
        state["optional_topics"], removed = remove_values(state["optional_topics"], args.topic)
        missing = [t for t in args.topic if t.lower().strip() not in {r.lower().strip() for r in removed}]
        if missing:
            warnings.append("optional_topics_not_found: " + ", ".join(missing))
        sync = args.sync_user
    elif args.command == "reprioritize":
        active_keys = {item.lower().strip() for item in state["active_topics"]}
        unknown = [item for item in args.topic if item.lower().strip() not in active_keys]
        if unknown:
            warnings.append("priority_topics_not_active: " + ", ".join(unknown))
        known = [item for item in args.topic if item.lower().strip() in active_keys]
        remaining = [item for item in state["active_topics"] if item.lower().strip() not in {k.lower().strip() for k in known}]
        state["user_priority"] = _dedupe(known + remaining)
        sync = args.sync_user
    elif args.command == "set-status":
        state["status"] = args.status
        if args.status == "configured":
            require_runnable_config(state)
        user_status = args.user_status or default_user_status_for_state(args.status)
        sync = args.sync_user
    else:
        raise ValueError(f"unsupported command: {args.command}")

    return state, user_status, sync, warnings


def add_topic_args(parser: argparse.ArgumentParser, required: bool = True) -> None:
    parser.add_argument("--topic", action="append", required=required, default=None, help="Topic value; repeat for multiple topics")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update Morning Report runtime state safely")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Path to current-topics.md")
    parser.add_argument("--user", default=str(DEFAULT_USER), help="Path to USER.md")
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG), help="Path to audit.log")
    parser.add_argument("--no-audit", action="store_true", help="Do not append an audit event")
    parser.add_argument("--dry-run", action="store_true", help="Print result without writing files")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="Write confirmed setup values")
    add_topic_args(setup)
    setup.add_argument("--optional-topic", action="append", default=[])
    setup.add_argument("--delivery-time", required=True)
    setup.add_argument("--timezone", required=True)
    setup.add_argument("--report-style", required=True)
    setup.add_argument("--report-language", required=True)
    setup.add_argument("--audio-summary", required=True)
    setup.add_argument("--delivery-channel", default="Telegram")
    setup.add_argument("--state-status", default="configured")
    setup.add_argument("--user-status", default="preferences_saved_schedule_pending")

    replace = sub.add_parser("replace-topics", help="Replace active topics")
    add_topic_args(replace)
    replace.add_argument("--optional-topic", action="append", default=None)
    replace.add_argument("--sync-user", action="store_true")

    for name in ["add-topic", "remove-topic", "add-optional-topic", "remove-optional-topic", "reprioritize"]:
        cmd = sub.add_parser(name, help=name.replace("-", " "))
        add_topic_args(cmd)
        cmd.add_argument("--sync-user", action="store_true")

    status = sub.add_parser("set-status", help="set lifecycle status without changing saved topics")
    status.add_argument("--status", required=True, choices=["configured", "paused", "disabled"])
    status.add_argument("--user-status", default=None)
    status.add_argument("--sync-user", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    state_path = Path(args.state)
    user_path = Path(args.user)
    state = read_state(state_path)
    user_prefs = read_user_prefs(user_path)
    try:
        validate_topic_args(args)
        state, user_status, sync, warnings = apply_command(args, state, user_prefs)
    except ConfigUpdateError as exc:
        print(
            json.dumps(
                {
                    "success": False,
                    "command": args.command,
                    "state_path": str(state_path),
                    "user_path": str(user_path),
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    result = {
        "command": args.command,
        "state_path": str(state_path),
        "user_path": str(user_path),
        "sync_user": sync,
        "warnings": warnings,
        "state": state,
    }

    if args.dry_run:
        result["rendered_state"] = render_state(state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    write_state(state_path, state)
    if sync:
        sync_user(user_path, user_status, state)
    if not args.no_audit:
        write_audit(
            Path(args.audit_log),
            "config_updated",
            {
                "command": args.command,
                "state_path": str(state_path),
                "user_path": str(user_path),
                "sync_user": sync,
                "user_status": user_status,
                "active_topics": state.get("active_topics", []),
                "optional_topics": state.get("optional_topics", []),
                "preferences": state.get("preferences", {}),
                "warnings": warnings,
            },
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
