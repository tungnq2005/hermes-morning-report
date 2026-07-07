"""Apply a confirmed Morning Report update preview."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any

from update.check_current_config import config_pref as pref

RUNNER_SCRIPT = "skills/morning-report/scripts/update/run.py"


def read_preview(path: Path | str) -> dict[str, Any]:
    preview_path = Path(path)
    if not preview_path.exists():
        raise FileNotFoundError(f"missing preview file: {preview_path}")
    data = json.loads(preview_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("phase") != "preview":
        raise ValueError(f"invalid preview file: {preview_path}")
    return data


def shell_command(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def runner_command(phase: str, args: argparse.Namespace, preview_file: Path | str) -> str:
    return shell_command(
        [
            "python3",
            RUNNER_SCRIPT,
            "--agent",
            "--work-dir",
            str(args.work_dir),
            phase,
            "--preview-file",
            str(preview_file),
        ]
    )


def scheduler_required(current: dict[str, Any], result: dict[str, Any]) -> bool:
    return (
        pref(current, "Delivery time") != pref(result, "Delivery time")
        or pref(current, "Timezone") != pref(result, "Timezone")
        or current.get("status") != result.get("status")
    )


def scheduler_action(current: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    if not scheduler_required(current, result):
        return None
    if current.get("status") != "configured" and result.get("status") == "configured":
        return {
            "required": True,
            "order": "verify_scheduler_then_save",
            "reference": "skills/morning-report/references/cron.md",
            "response_action": (
                "Inspect, enable or recreate, and verify the Morning Report scheduler before saving enabled status."
            ),
        }
    return {
        "required": True,
        "order": "save_then_verify_scheduler",
        "reference": "skills/morning-report/references/cron.md",
        "response_action": (
            "After save succeeds, inspect the existing Morning Report scheduler, apply the required change, and verify it."
        ),
    }


def apply_phase(args: argparse.Namespace) -> dict[str, Any]:
    preview = read_preview(args.preview_file)
    current = preview["current_config"]
    result = preview["resulting_config"]
    schedule = scheduler_action(current, result)
    save_command = runner_command("save", args, args.preview_file)

    if schedule and schedule["order"] == "verify_scheduler_then_save":
        next_action = {
            "type": "verify_scheduler_before_save",
            "scheduler_action": schedule,
            "after_scheduler": {
                "command": save_command,
            },
            "response_action": (
                "Use cron.md to verify scheduler first. Run after_scheduler.command only after scheduler verification succeeds."
            ),
        }
    else:
        next_action = {
            "type": "save_update",
            "command": save_command,
            "response_action": "Save the confirmed Morning Report configuration.",
        }
        if schedule:
            next_action["scheduler_action_after_save"] = schedule

    return {
        "success": True,
        "phase": "apply",
        "can_continue": True,
        "preview_file": str(args.preview_file),
        "changed_fields": preview.get("changed_fields", []),
        "display_config": preview.get("display_config", {}),
        "scheduler_action": schedule,
        "next_action": next_action,
    }
