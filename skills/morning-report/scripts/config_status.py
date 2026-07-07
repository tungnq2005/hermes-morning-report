#!/usr/bin/env python3
"""Report Morning Report configuration status as JSON.

This helper is used by the agent. It reads the runtime state file and USER.md,
then reports whether Morning Report has the minimum configuration required to run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from report_style import report_style_info

SKILL_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = SKILL_DIR.parent.parent
DEFAULT_STATE = SKILL_DIR / "state" / "current-topics.md"
DEFAULT_USER = WORKSPACE / "USER.md"

REQUIRED_PREFS = [
    "Delivery time",
    "Timezone",
    "Report style",
    "Report language",
    "Audio summary",
    "Delivery channel",
]

DEFAULT_SETUP_VALUES = {
    "audio_summary": "Enabled",
    "delivery_channel": "Telegram",
}


def _section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def _numbered_items(section: str) -> list[str]:
    items: list[str] = []
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


def parse_state(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    status_match = re.search(r"^Status:\s*(.+?)\s*$", text, re.MULTILINE)
    prefs = _bullet_map(_section(text, "Report preferences"))
    style_info = report_style_info(prefs.get("Report style", "")) if prefs.get("Report style") else {}
    return {
        "path": str(path),
        "exists": path.exists(),
        "setup_status": status_match.group(1).strip() if status_match else "not_configured",
        "active_topics": _numbered_items(_section(text, "Active topics")),
        "optional_topics": _optional_items(_section(text, "Optional topics")),
        "user_priority": _numbered_items(_section(text, "User priority")),
        "report_preferences": prefs,
        "report_style": style_info,
    }


def parse_user(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    prefs = _bullet_map(_section(text, "Morning Report Preferences"))
    timezone = ""
    for line in text.splitlines():
        match = re.match(r"^\s*-\s+(.+?):\s*(.*?)\s*$", line)
        if not match:
            continue
        label = re.sub(r"[*_`]", "", match.group(1)).strip().lower()
        if label == "timezone":
            timezone = re.sub(r"^[*_`\s]+", "", match.group(2)).strip()
            break
    return {
        "path": str(path),
        "exists": path.exists(),
        "morning_report_preferences": prefs,
        "user_context": {
            "timezone": timezone,
        },
    }


def setup_action(state: dict[str, Any], user: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    prefs = state["report_preferences"]
    user_prefs = user.get("morning_report_preferences", {})
    user_context = user.get("user_context", {})

    def pref_value(key: str) -> str:
        return prefs.get(key) or user_prefs.get(key, "")

    topics = state["active_topics"]
    if not topics and user_prefs.get("Topics"):
        topics = [item.strip() for item in user_prefs["Topics"].split(",") if item.strip()]

    timezone = pref_value("Timezone") or user_context.get("timezone", "")
    report_style = pref_value("Report style")
    report_style_valid = report_style_info(report_style).get("valid") if report_style else False

    known_fields: dict[str, Any] = {}
    if topics:
        known_fields["topics"] = topics
    if pref_value("Delivery time"):
        known_fields["delivery_time"] = pref_value("Delivery time")
    if timezone:
        known_fields["timezone"] = timezone
    if report_style:
        known_fields["report_style"] = report_style
    if pref_value("Report language"):
        known_fields["report_language"] = pref_value("Report language")
    if pref_value("Audio summary"):
        known_fields["audio_summary"] = pref_value("Audio summary")
    if pref_value("Delivery channel"):
        known_fields["delivery_channel"] = pref_value("Delivery channel")

    missing_fields: list[str] = []
    if not topics:
        missing_fields.append("topics")
    if not pref_value("Delivery time"):
        missing_fields.append("delivery_time")
    if not timezone:
        missing_fields.append("timezone")
    if not report_style or not report_style_valid:
        missing_fields.append("report_style")
    if not pref_value("Report language"):
        missing_fields.append("report_language")

    action = {
        "language": "match_user",
        "known_fields": known_fields,
        "missing_fields": missing_fields,
        "defaults": DEFAULT_SETUP_VALUES,
        "optional_overrides": ["audio_summary"],
        "rules": [
            "Ask only for missing_fields.",
            "If the reply is unrelated or unclear, ask again only for unresolved fields.",
            "Do not save until the full config is clearly confirmed.",
        ],
    }
    if not missing_fields and not missing:
        return {
            "type": "config_ready",
            "can_continue": True,
            "user_message_goal": "Confirm that Morning Report preferences are already available.",
            **action,
        }
    if not missing_fields:
        return {
            "type": "confirm_known_config_before_save",
            "can_continue": False,
            "user_message_goal": (
                "Show the known Morning Report preferences and ask for confirmation before saving or repairing runtime state."
            ),
            **action,
        }
    return {
        "type": "collect_missing_config",
        "can_continue": False,
        "user_message_goal": "Collect missing Morning Report preferences naturally before saving anything.",
        **action,
    }


def build_status(state_path: Path, user_path: Path) -> dict[str, Any]:
    state = parse_state(state_path)
    user = parse_user(user_path)
    prefs = state["report_preferences"]

    missing: list[str] = []
    if not state["exists"]:
        missing.append("state_file")
    if state["setup_status"] != "configured":
        missing.append("Status: configured")
    if not state["active_topics"]:
        missing.append("Active topics")
    for key in REQUIRED_PREFS:
        if not prefs.get(key):
            missing.append(key)
    if prefs.get("Report style") and not state.get("report_style", {}).get("valid"):
        missing.append("supported Report style")

    warnings: list[str] = []
    if state.get("report_style") and not state["report_style"].get("valid"):
        warnings.append(state["report_style"].get("error", "unsupported_report_style"))
    user_prefs = user["morning_report_preferences"]
    if user_prefs:
        state_topics = ", ".join(state["active_topics"])
        comparisons = {
            "Topics": state_topics,
            "Delivery time": prefs.get("Delivery time", ""),
            "Timezone": prefs.get("Timezone", ""),
            "Report style": prefs.get("Report style", ""),
            "Report language": prefs.get("Report language", ""),
            "Audio summary": prefs.get("Audio summary", ""),
            "Delivery channel": prefs.get("Delivery channel", ""),
        }
        for key, value in comparisons.items():
            user_value = user_prefs.get(key, "")
            if user_value and value and user_value != value:
                warnings.append(f"USER.md mismatch for {key}: {user_value!r} != {value!r}")

    return {
        "configured": not missing,
        "missing_required": missing,
        "warnings": warnings,
        "state": state,
        "user": user,
        "setup_action": setup_action(state, user, missing),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Morning Report configuration status as JSON")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Path to current-topics.md")
    parser.add_argument("--user", default=str(DEFAULT_USER), help="Path to USER.md")
    parser.add_argument("--check", action="store_true", help="Exit 0 only when configuration is runnable")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    args = parser.parse_args()

    status = build_status(Path(args.state), Path(args.user))
    indent = None if args.compact else 2
    print(json.dumps(status, ensure_ascii=False, indent=indent))
    if args.check and not status["configured"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
