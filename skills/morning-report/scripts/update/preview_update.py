"""Preview Morning Report configuration updates without writing files."""

from __future__ import annotations

import argparse
import copy
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_style import report_style_info, suggest_report_style
from update.check_current_config import check_current_config, config_pref as pref, display_config
from update_config import PREF_KEYS

RUNNER_SCRIPT = "skills/morning-report/scripts/update/run.py"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def shell_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def normalize_status(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    aliases = {
        "enabled": "configured",
        "enable": "configured",
        "resume": "configured",
        "resumed": "configured",
        "configured": "configured",
        "paused": "paused",
        "pause": "paused",
        "disabled": "disabled",
        "disable": "disabled",
    }
    if key not in aliases:
        raise ValueError("unsupported_status: use configured, paused, or disabled")
    return aliases[key]


def normalize_audio(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    aliases = {
        "enabled": "Enabled",
        "enable": "Enabled",
        "on": "Enabled",
        "true": "Enabled",
        "yes": "Enabled",
        "disabled": "Disabled",
        "disable": "Disabled",
        "off": "Disabled",
        "false": "Disabled",
        "no": "Disabled",
    }
    if key not in aliases:
        raise ValueError("unclear_audio_summary: use Enabled or Disabled")
    return aliases[key]


def style_preview(raw: str) -> tuple[str, dict[str, Any] | None]:
    suggestion = suggest_report_style(raw)
    if suggestion.get("needs_confirmation"):
        return str(suggestion["canonical"]), {
            "type": "confirm_style",
            "can_continue": False,
            "style_suggestion": suggestion,
            "response_action": (
                "Ask whether the user means the suggested report style before saving any update."
            ),
        }
    return str(suggestion["canonical"]), None


def apply_requested_changes(config: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = copy.deepcopy(config)
    prefs = result["preferences"]

    if args.replace_topic:
        result["topics"] = dedupe(args.replace_topic)
        result["user_priority"] = list(result["topics"])
    if args.add_topic:
        result["topics"] = dedupe(result["topics"] + args.add_topic)
        result["user_priority"] = dedupe(result.get("user_priority", []) + args.add_topic)
    if args.remove_topic:
        remove_keys = {topic.strip().lower() for topic in args.remove_topic}
        result["topics"] = [topic for topic in result["topics"] if topic.strip().lower() not in remove_keys]
        result["user_priority"] = [
            topic for topic in result.get("user_priority", []) if topic.strip().lower() not in remove_keys
        ]
    if args.add_optional_topic:
        result["optional_topics"] = dedupe(result["optional_topics"] + args.add_optional_topic)
    if args.remove_optional_topic:
        remove_keys = {topic.strip().lower() for topic in args.remove_optional_topic}
        result["optional_topics"] = [
            topic for topic in result["optional_topics"] if topic.strip().lower() not in remove_keys
        ]
    if args.reprioritize_topic:
        active_keys = {topic.strip().lower() for topic in result["topics"]}
        known = [topic for topic in args.reprioritize_topic if topic.strip().lower() in active_keys]
        known_keys = {topic.strip().lower() for topic in known}
        remaining = [topic for topic in result["topics"] if topic.strip().lower() not in known_keys]
        result["topics"] = dedupe(known + remaining)
        result["user_priority"] = list(result["topics"])

    if args.delivery_time:
        prefs["Delivery time"] = args.delivery_time.strip()
    if args.timezone:
        prefs["Timezone"] = args.timezone.strip()
    if args.report_style:
        canonical, action = style_preview(args.report_style)
        prefs["Report style"] = canonical
        if action:
            return result, action
    if args.report_language:
        prefs["Report language"] = args.report_language.strip()
    if args.audio_summary:
        prefs["Audio summary"] = normalize_audio(args.audio_summary)
    if args.delivery_channel:
        prefs["Delivery channel"] = args.delivery_channel.strip()
    if args.status:
        result["status"] = normalize_status(args.status)

    return result, None


def changed_fields(current: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        ("status", "Status"),
        ("topics", "Topics"),
        ("optional_topics", "Optional topics"),
    ]
    changes: list[dict[str, Any]] = []
    for key, label in fields:
        if current.get(key) != result.get(key):
            changes.append({"field": label, "current": current.get(key), "requested": result.get(key)})
    for key in PREF_KEYS:
        old = pref(current, key)
        new = pref(result, key)
        if old != new:
            changes.append({"field": key, "current": old, "requested": new})
    return changes


def validation_errors(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not config["topics"]:
        errors.append("active_topics_required")
    for key in PREF_KEYS:
        if not pref(config, key):
            errors.append(f"missing_preference:{key}")
    style_value = pref(config, "Report style")
    if style_value and not report_style_info(style_value).get("valid"):
        errors.append("unsupported_report_style")
    return errors


def preview_path(args: argparse.Namespace) -> Path:
    return Path(args.work_dir) / "preview.json"


def write_preview_manifest(
    *,
    args: argparse.Namespace,
    current: dict[str, Any],
    result: dict[str, Any],
    changes: list[dict[str, Any]],
) -> Path:
    path = preview_path(args)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "success": True,
        "phase": "preview",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "state": str(args.state),
            "user": str(args.user),
            "audit_log": str(args.audit_log),
            "work_dir": str(args.work_dir),
        },
        "current_config": current,
        "resulting_config": result,
        "current_display_config": display_config(current),
        "display_config": display_config(result),
        "changed_fields": changes,
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def apply_command(args: argparse.Namespace, manifest_path: Path) -> str:
    return shell_command(
        [
            "python3",
            RUNNER_SCRIPT,
            "--agent",
            "--work-dir",
            str(args.work_dir),
            "apply",
            "--preview-file",
            str(manifest_path),
        ]
    )


def preview(args: argparse.Namespace) -> dict[str, Any]:
    current_check = check_current_config(args.state, args.user)
    current = current_check["current_config"]
    missing = current_check["missing"]
    if missing:
        return {
            "success": False,
            "phase": "preview",
            "can_continue": False,
            "error": "setup_required_before_update",
            "missing": missing,
            "current_config": current,
            "current_display_config": current_check["current_display_config"],
            "next_action": {
                "type": "respond_and_stop",
                "response_action": "Tell the user Morning Report setup is incomplete and route them to setup.",
            },
        }

    try:
        result, blocked_action = apply_requested_changes(current, args)
    except ValueError as exc:
        return {
            "success": False,
            "phase": "preview",
            "can_continue": False,
            "error": str(exc),
            "current_config": current,
            "current_display_config": display_config(current),
            "next_action": {
                "type": "ask_clarification",
                "response_action": "Ask the user to clarify the unclear update value.",
            },
        }

    changes = changed_fields(current, result)
    if blocked_action:
        return {
            "success": True,
            "phase": "preview",
            "can_continue": False,
            "current_config": current,
            "resulting_config": result,
            "current_display_config": display_config(current),
            "display_config": display_config(result),
            "changed_fields": changes,
            "next_action": blocked_action,
        }

    errors = validation_errors(result)
    if errors:
        return {
            "success": False,
            "phase": "preview",
            "can_continue": False,
            "error": "invalid_resulting_config",
            "details": errors,
            "current_config": current,
            "resulting_config": result,
            "current_display_config": display_config(current),
            "display_config": display_config(result),
            "next_action": {
                "type": "respond_and_stop",
                "response_action": "Explain the invalid update and ask for a valid replacement.",
            },
        }

    if not changes:
        return {
            "success": True,
            "phase": "preview",
            "can_continue": False,
            "current_config": current,
            "resulting_config": result,
            "current_display_config": display_config(current),
            "display_config": display_config(result),
            "changed_fields": [],
            "next_action": {
                "type": "report_no_change",
                "response_action": "Tell the user the saved Morning Report config already matches the request.",
            },
        }

    manifest_path = write_preview_manifest(args=args, current=current, result=result, changes=changes)
    next_action: dict[str, Any] = {
        "type": "confirm_update",
        "can_continue": False,
        "response_action": (
            "Show changed_fields plus display_config. Wait for clear confirmation before running after_confirmation.command."
        ),
        "after_confirmation": {
            "command": apply_command(args, manifest_path),
        },
    }

    return {
        "success": True,
        "phase": "preview",
        "can_continue": False,
        "preview_file": str(manifest_path),
        "current_config": current,
        "resulting_config": result,
        "current_display_config": display_config(current),
        "display_config": display_config(result),
        "changed_fields": changes,
        "requires_confirmation": True,
        "next_action": next_action,
    }
