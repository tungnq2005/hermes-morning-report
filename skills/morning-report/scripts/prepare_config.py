#!/usr/bin/env python3
"""Prepare Morning Report setup/update flow from current config."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from helpers.check_topic_config import DEFAULT_CONFIG_PATH, check_topic_config

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
OUTPUT_TEMPLATES_PATH = SKILL_DIR / "references" / "workflow-output-templates.json"
CRON_JOB_NAME = "Morning Report"
CRON_PROMPT = "Follow the Run Report workflow in SKILL.md."
CRON_SKILL = "morning-report"

PREFERENCE_FIELDS = [
    "delivery_time",
    "timezone",
    "report_style",
    "report_language",
    "audio_summary",
    "delivery_channel",
]

REQUEST_FIELD_ORDER = [
    "topic",
    *PREFERENCE_FIELDS,
]


def load_config_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_config_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_requested_config(args: argparse.Namespace) -> dict[str, Any]:
    requested = {
        "topic": args.topic,
        "delivery_time": args.delivery_time,
        "timezone": args.timezone,
        "report_style": args.report_style,
        "report_language": args.report_language,
        "audio_summary": args.audio_summary,
        "delivery_channel": args.delivery_channel,
    }
    return {key: value for key, value in requested.items() if value is not None}


def apply_requested_config(data: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    candidate = copy.deepcopy(data) if isinstance(data, dict) else {}

    if "topic" in requested:
        candidate["topic"] = requested["topic"]

    for field in PREFERENCE_FIELDS:
        if field in requested:
            candidate[field] = requested[field]

    return candidate


def saved_config_data(candidate_data: dict[str, Any], candidate_check: dict[str, Any]) -> dict[str, Any]:
    saved = copy.deepcopy(candidate_data)
    available = candidate_check["available_config"]

    if "topic" in available:
        saved["topic"] = available["topic"]

    for field in PREFERENCE_FIELDS:
        if field in available:
            saved[field] = available[field]

    return saved


def requested_config_bullets(
    current_config: dict[str, Any],
    candidate_config: dict[str, Any],
    requested: dict[str, Any],
) -> str:
    bullets: list[str] = []
    for field in REQUEST_FIELD_ORDER:
        if field not in requested:
            continue
        old_value = current_config.get(field)
        new_value = candidate_config.get(field, requested[field])
        if old_value and old_value != new_value:
            bullets.append(f"• {field}: {old_value} → {new_value}")
        else:
            bullets.append(f"• {field}: {new_value}")
    return "\n".join(bullets)


def cron_sync_required(current_config: dict[str, Any], candidate_config: dict[str, Any]) -> bool:
    if not current_config.get("delivery_time") or not current_config.get("timezone"):
        return False
    if not candidate_config.get("delivery_time") or not candidate_config.get("timezone"):
        return False
    return (
        current_config["delivery_time"] != candidate_config["delivery_time"]
        or current_config["timezone"] != candidate_config["timezone"]
    )


def local_time_to_utc_cron(delivery_time: str, tz_name: str) -> str:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", delivery_time.strip())
    if not match:
        raise ValueError("delivery_time must use HH:MM format")

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("delivery_time must be a valid 24-hour time")

    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {tz_name}") from exc

    local_dt = datetime.now(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
    utc_dt = local_dt.astimezone(timezone.utc)
    return f"{utc_dt.minute} {utc_dt.hour} * * *"


def find_morning_report_job_id(cron_list_output: str) -> str | None:
    current_job_id: str | None = None
    for line in cron_list_output.splitlines():
        job_match = re.match(r"\s+([0-9a-f]{8,})\s+\[[^\]]+\]", line)
        if job_match:
            current_job_id = job_match.group(1)
            continue

        if current_job_id and line.strip().startswith("Name:"):
            name = line.split(":", 1)[1].strip()
            if name == CRON_JOB_NAME:
                return current_job_id

    return None


def sync_cron_if_needed(
    state_path: Path,
    current_config: dict[str, Any],
    candidate_config: dict[str, Any],
    enable_cron: bool = False,
) -> str:
    update_required = cron_sync_required(current_config, candidate_config)
    if not enable_cron and not update_required:
        return ""

    try:
        schedule = local_time_to_utc_cron(
            str(candidate_config["delivery_time"]),
            str(candidate_config["timezone"]),
        )
    except ValueError as exc:
        return f"Cron schedule was not updated because {exc}."

    if state_path.resolve() != DEFAULT_CONFIG_PATH.resolve():
        return f"Cron schedule was not updated because --state is not the default config path. Required schedule: {schedule}."

    list_result = subprocess.run(
        ["hermes", "cron", "list", "--all"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if list_result.returncode != 0:
        error = (list_result.stderr or list_result.stdout).strip()
        return f"Cron schedule was not updated because `hermes cron list --all` failed: {error}"

    job_id = find_morning_report_job_id(list_result.stdout)
    if not job_id and not enable_cron:
        return f"No existing Morning Report cron job was found. Create one with schedule `{schedule}` if the user wants daily delivery."

    if job_id:
        edit_result = subprocess.run(
            ["hermes", "cron", "--accept-hooks", "edit", job_id, "--schedule", schedule],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if edit_result.returncode != 0:
            error = (edit_result.stderr or edit_result.stdout).strip()
            return f"Cron schedule was not updated because `hermes cron edit` failed: {error}"

        return f"Morning Report cron schedule was updated to `{schedule}`."

    create_result = subprocess.run(
        [
            "hermes",
            "cron",
            "--accept-hooks",
            "create",
            "--name",
            CRON_JOB_NAME,
            "--skill",
            CRON_SKILL,
            schedule,
            CRON_PROMPT,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if create_result.returncode != 0:
        error = (create_result.stderr or create_result.stdout).strip()
        return f"Cron schedule was not created because `hermes cron create` failed: {error}"

    return f"Morning Report cron schedule was created with `{schedule}`."


def render_next_action(
    configured: bool,
    requested_bullets: str,
    save: bool,
    cron_sync_message: str = "",
) -> str:
    data = json.loads(OUTPUT_TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = data["steps"]["prepare_config"]
    if save:
        template_name = "saved" if configured else "save_blocked"
    else:
        template_name = "configured" if configured else "needs_config"
    template = templates[template_name]["next_action"]
    requested_section = ""
    if requested_bullets:
        requested_section = f"\nYou MUST present the following changes as bullets:\n{requested_bullets}\n"
    cron_sync_section = ""
    if cron_sync_message:
        cron_sync_section = f"\nCron sync result: {cron_sync_message}\n"
    return (
        template
        .replace("{requested_config_section}", requested_section)
        .replace("{cron_sync_section}", cron_sync_section)
    )


def render_prepare_output(
    state_path: Path,
    requested: dict[str, Any],
    save: bool = False,
    enable_cron: bool = False,
) -> dict[str, Any]:
    current_check = check_topic_config(state_path)
    current_data = load_config_data(state_path)
    candidate_data = apply_requested_config(current_data, requested)
    candidate_check = check_topic_config(candidate_data)
    requested_bullets = requested_config_bullets(
        current_check["available_config"],
        candidate_check["available_config"],
        requested,
    )

    cron_sync_message = ""
    if save and candidate_check["configured"]:
        save_config_data(state_path, saved_config_data(candidate_data, candidate_check))
        cron_sync_message = sync_cron_if_needed(
            state_path,
            current_check["available_config"],
            candidate_check["available_config"],
            enable_cron=enable_cron,
        )

    return {
        "configured": candidate_check["configured"],
        "available_config": candidate_check["available_config"],
        "missing_config": candidate_check["missing_config"],
        "next_action": render_next_action(
            candidate_check["configured"],
            requested_bullets,
            save,
            cron_sync_message,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Morning Report config setup/update")
    parser.add_argument("--state", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--enable-cron", action="store_true")
    parser.add_argument("--topic")
    parser.add_argument("--delivery-time", dest="delivery_time")
    parser.add_argument("--timezone")
    parser.add_argument("--report-style", dest="report_style")
    parser.add_argument("--report-language", dest="report_language")
    parser.add_argument("--audio-summary", dest="audio_summary")
    parser.add_argument("--delivery-channel", dest="delivery_channel")
    args = parser.parse_args()
    state_path = Path(args.state)

    print(
        json.dumps(
            render_prepare_output(
                state_path,
                collect_requested_config(args),
                save=args.save,
                enable_cron=args.enable_cron,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
