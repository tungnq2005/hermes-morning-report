"""Save a confirmed Morning Report update preview and verify config state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from update.apply_confirmed_update import read_preview, scheduler_action

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
UPDATE_CONFIG = SCRIPTS_DIR / "update_config.py"
CONFIG_STATUS = SCRIPTS_DIR / "config_status.py"


def user_status_for_state(state_status: str) -> str:
    if state_status == "configured":
        return "enabled"
    return state_status


def update_config_command(preview: dict[str, Any]) -> list[str]:
    result = preview["resulting_config"]
    paths = preview["paths"]
    parts = [
        sys.executable,
        str(UPDATE_CONFIG),
        "--state",
        paths["state"],
        "--user",
        paths["user"],
        "--audit-log",
        paths["audit_log"],
        "setup",
    ]
    for topic in result["topics"]:
        parts.extend(["--topic", topic])
    for topic in result["optional_topics"]:
        parts.extend(["--optional-topic", topic])

    prefs = result["preferences"]
    parts.extend(
        [
            "--delivery-time",
            prefs["Delivery time"],
            "--timezone",
            prefs["Timezone"],
            "--report-style",
            prefs["Report style"],
            "--report-language",
            prefs["Report language"],
            "--audio-summary",
            prefs["Audio summary"],
            "--delivery-channel",
            prefs["Delivery channel"],
            "--state-status",
            result["status"],
            "--user-status",
            user_status_for_state(result["status"]),
        ]
    )
    return parts


def verify_command(preview: dict[str, Any]) -> list[str]:
    result = preview["resulting_config"]
    paths = preview["paths"]
    parts = [
        sys.executable,
        str(CONFIG_STATUS),
        "--state",
        paths["state"],
        "--user",
        paths["user"],
    ]
    if result["status"] == "configured":
        parts.append("--check")
    return parts


def run_json(command: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = completed.stdout.strip()
    data: dict[str, Any] | None = None
    if output.startswith("{"):
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = None
    error = completed.stderr.strip() or completed.stdout.strip()
    return completed.returncode, data, error


def save_phase(args: argparse.Namespace) -> dict[str, Any]:
    preview = read_preview(args.preview_file)
    current = preview["current_config"]
    result = preview["resulting_config"]

    update_code, update_result, update_error = run_json(update_config_command(preview))
    if update_code != 0:
        return {
            "success": False,
            "phase": "save",
            "can_continue": False,
            "preview_file": str(args.preview_file),
            "error": update_error,
            "next_action": {
                "type": "respond_and_stop",
                "response_action": "Tell the user the confirmed update could not be saved.",
            },
        }

    verify_code, verify_result, verify_error = run_json(verify_command(preview))
    saved = verify_code == 0
    schedule = scheduler_action(current, result)
    next_action: dict[str, Any]
    if not saved:
        next_action = {
            "type": "respond_and_stop",
            "response_action": "Tell the user the update was written but config verification failed.",
        }
    elif schedule and schedule["order"] == "save_then_verify_scheduler":
        next_action = {
            "type": "verify_scheduler_after_save",
            "scheduler_action": schedule,
            "response_action": "Use cron.md to update and verify the Morning Report scheduler before final confirmation.",
        }
    else:
        next_action = {
            "type": "done",
            "response_action": "Confirm the Morning Report configuration was updated.",
        }

    return {
        "success": saved,
        "phase": "save",
        "can_continue": saved and bool(schedule and schedule["order"] == "save_then_verify_scheduler"),
        "preview_file": str(args.preview_file),
        "changed_fields": preview.get("changed_fields", []),
        "display_config": preview.get("display_config", {}),
        "update_result": update_result,
        "verify_result": verify_result,
        "verify_error": verify_error if not saved else "",
        "scheduler_action": schedule,
        "next_action": next_action,
    }
