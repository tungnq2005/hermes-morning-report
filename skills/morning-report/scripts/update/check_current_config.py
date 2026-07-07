"""Check current Morning Report update configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from config_status import build_status
from update_config import PREF_KEYS


def config_pref(config: dict[str, Any], key: str) -> str:
    return str(config.get("preferences", {}).get(key, "")).strip()


def display_config(config: dict[str, Any]) -> dict[str, Any]:
    prefs = config.get("preferences", {})
    return {
        "Status": config.get("status", ""),
        "Topics": config.get("topics", []),
        "Optional topics": config.get("optional_topics", []),
        "Delivery time": prefs.get("Delivery time", ""),
        "Timezone": prefs.get("Timezone", ""),
        "Report style": prefs.get("Report style", ""),
        "Report language": prefs.get("Report language", ""),
        "Audio summary": prefs.get("Audio summary", ""),
        "Delivery channel": prefs.get("Delivery channel", ""),
    }


def state_to_config(status: dict[str, Any]) -> dict[str, Any]:
    state = status["state"]
    prefs = state.get("report_preferences", {})
    style_info = state.get("report_style", {})
    report_style = (
        str(style_info.get("canonical", ""))
        if style_info.get("valid")
        else prefs.get("Report style", "")
    )
    return {
        "status": state.get("setup_status", "not_configured"),
        "topics": list(state.get("active_topics") or []),
        "optional_topics": list(state.get("optional_topics") or []),
        "user_priority": list(state.get("user_priority") or state.get("active_topics") or []),
        "preferences": {
            "Delivery time": prefs.get("Delivery time", ""),
            "Timezone": prefs.get("Timezone", ""),
            "Report style": report_style,
            "Report language": prefs.get("Report language", ""),
            "Audio summary": prefs.get("Audio summary", ""),
            "Delivery channel": prefs.get("Delivery channel", ""),
        },
    }


def missing_saved_config(config: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not config["topics"]:
        missing.append("topics")
    for key in PREF_KEYS:
        if not config_pref(config, key):
            missing.append(key)
    if config["status"] == "not_configured":
        missing.append("status")
    return missing


def check_current_config(state_path: Path | str, user_path: Path | str) -> dict[str, Any]:
    status = build_status(Path(state_path), Path(user_path))
    current = state_to_config(status)
    missing = missing_saved_config(current)
    can_continue = not missing
    return {
        "success": can_continue,
        "phase": "check-config",
        "can_continue": can_continue,
        "missing": missing,
        "current_config": current,
        "current_display_config": display_config(current),
        "next_action": (
            {
                "type": "preview_update",
                "response_action": "Extract only explicit user-requested update flags, then run command_template.",
                "command_template": "python3 skills/morning-report/scripts/update/run.py --agent preview <flags>",
            }
            if can_continue
            else {
                "type": "respond_and_stop",
                "response_action": "Tell the user Morning Report setup is incomplete and route them to setup.",
            }
        ),
    }


def check_config_phase(args: argparse.Namespace) -> dict[str, Any]:
    return check_current_config(Path(args.state), Path(args.user))
