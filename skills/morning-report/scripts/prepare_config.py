#!/usr/bin/env python3
"""Prepare Morning Report setup/update flow (per-topic config) from current config.

Config schema (per-topic): {"topics": [ {topic, delivery_time, timezone,
report_style, report_language, audio_summary, delivery_channel}, ... ]}.
Every preference field is owned by each topic, so each topic maps to its own
cron job and its own delivered report.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from helpers.check_topic_config import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_TOPIC_CONFIG,
    PREFERENCE_FIELDS,
    check_topic_config,
    normalize_config,
    normalize_topics,
)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
OUTPUT_TEMPLATES_PATH = SKILL_DIR / "references" / "workflow-output-templates.json"
CRON_JOB_PREFIX = "Morning Report"
CRON_JOB_NAME = "Morning Report"  # legacy single combined job, removed on reconcile
CRON_SKILL = "morning-report"
CRON_PROMPT_TEMPLATE = (
    "Follow the Run Report workflow in SKILL.md for only the topic '{topic}'. "
    "Do not process other topics. Run collect_sources.py with --topic '{topic}' once, "
    "then Step 3 and Step 4. "
    "Your final response MUST START with the report's title line (the '# ' heading) and "
    "contain ONLY: the report.md content verbatim (including the ### Sources footer), "
    "then a line MEDIA:<the MP3 output path you passed to generate_audio_file.py in Step 4>. "
    "Do NOT write any line before the title — no 'All steps complete', no 'Delivering the final report', "
    "no 'Here is the report', no progress or announcement text, no summary."
)


# ── Config load / save ─────────────────────────────────────────────────
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
    normalized = normalize_config(data if isinstance(data, dict) else {})
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_requested_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "topic": args.topic,
        "all_topics": args.all_topics,
        "add_topics": args.add_topic,
        "remove_topics": args.remove_topic,
        "delivery_time": args.delivery_time,
        "timezone": args.timezone,
        "report_style": args.report_style,
        "report_language": args.report_language,
        "audio_summary": args.audio_summary,
        "delivery_channel": args.delivery_channel,
    }


def _field_changes(requested: dict[str, Any]) -> dict[str, Any]:
    return {field: requested[field] for field in PREFERENCE_FIELDS if requested.get(field) is not None}


def apply_requested_config(data: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    current = normalize_config(data if isinstance(data, dict) else {})
    topics: list[dict[str, Any]] = [dict(t) for t in current["topics"]]
    changes = _field_changes(requested)

    if requested.get("remove_topics"):
        remove_keys = {t.casefold() for t in normalize_topics(requested["remove_topics"])}
        topics = [t for t in topics if t["topic"].casefold() not in remove_keys]

    if requested.get("add_topics"):
        existing_keys = {t["topic"].casefold() for t in topics}
        defaults = {k: v for k, v in (topics[0] if topics else DEFAULT_TOPIC_CONFIG).items() if k != "topic"}
        for new_name in normalize_topics(requested["add_topics"]):
            key = new_name.casefold()
            if key in existing_keys:
                continue
            new_obj: dict[str, Any] = {"topic": new_name}
            new_obj.update(defaults)
            topics.append(new_obj)
            existing_keys.add(key)

    if changes:
        if requested.get("all_topics"):
            for t in topics:
                t.update(changes)
        elif requested.get("topic"):
            target_key = requested["topic"].casefold()
            for t in topics:
                if t["topic"].casefold() == target_key:
                    t.update(changes)

    return {"topics": topics}


def saved_config_data(candidate_check: dict[str, Any]) -> dict[str, Any]:
    return {"topics": copy.deepcopy(candidate_check["available_config"]["topics"])}


def _append_field_bullets(
    bullets: list[str], new_obj: dict[str, Any], old_obj: dict[str, Any], changes: dict[str, Any]
) -> None:
    label = new_obj["topic"]
    for field in PREFERENCE_FIELDS:
        if field in changes:
            old = old_obj.get(field)
            new = new_obj.get(field)
            if old and old != new:
                bullets.append(f"• [{label}] {field}: {old} → {new}")
            else:
                bullets.append(f"• [{label}] {field}: {new}")


def requested_review(
    current_data: dict[str, Any],
    candidate_data: dict[str, Any],
    requested: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Return (bullets, warnings) describing the requested change vs current."""
    current_list = normalize_config(current_data if isinstance(current_data, dict) else {})["topics"]
    current_by_key = {t["topic"].casefold(): t for t in current_list}
    candidate_list = normalize_config(candidate_data)["topics"]
    cand_by_key = {t["topic"].casefold(): t for t in candidate_list}

    bullets: list[str] = []
    warnings: list[str] = []
    changes = _field_changes(requested)

    if requested.get("add_topics"):
        for name in normalize_topics(requested["add_topics"]):
            if name.casefold() in current_by_key:
                warnings.append(f"• Topic '{name}' already exists; not added again.")
            else:
                bullets.append(f"• add topic: {name}")

    if requested.get("remove_topics"):
        for name in normalize_topics(requested["remove_topics"]):
            if name.casefold() in current_by_key:
                bullets.append(f"• remove topic: {name}")
            else:
                warnings.append(f"• Topic '{name}' is not configured; cannot remove.")

    if changes:
        if requested.get("all_topics"):
            for t in candidate_list:
                _append_field_bullets(bullets, t, current_by_key.get(t["topic"].casefold(), {}), changes)
        elif requested.get("topic"):
            key = requested["topic"].casefold()
            if key not in current_by_key:
                warnings.append(f"• Topic '{requested['topic']}' is not configured. Add it first with --add-topic.")
            elif key in cand_by_key:
                _append_field_bullets(bullets, cand_by_key[key], current_by_key[key], changes)
        else:
            warnings.append("• Field changes need a target: specify --topic \"<topic>\" or --all-topics.")

    return bullets, warnings


# ── Cron helpers ───────────────────────────────────────────────────────
def cron_job_name_for_topic(topic: str) -> str:
    return f"{CRON_JOB_PREFIX} - {topic}"


def cron_prompt_for_topic(topic: str) -> str:
    return CRON_PROMPT_TEMPLATE.format(topic=topic)


HERMES_CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"
_HERMES_CONFIG_TZ_RE = re.compile(r"""^timezone:\s*['"]?([A-Za-z0-9_+\-/]+)['"]?\s*(?:#.*)?$""")


def hermes_config_timezone(config_path: Path | None = None) -> str:
    """Read the top-level `timezone:` key from ~/.hermes/config.yaml.

    Deliberately a line-level regex instead of a YAML parse: this skill must run
    on macOS system Python with no third-party packages installed, and Hermes'
    own `timezone` key is always a top-level scalar.
    """
    path = HERMES_CONFIG_PATH if config_path is None else config_path
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        match = _HERMES_CONFIG_TZ_RE.match(line.strip("﻿"))
        if match:
            return match.group(1)
    return ""


def hermes_effective_timezone(config_path: Path | None = None) -> str:
    """Return the IANA timezone Hermes evaluates cron expressions in.

    Mirrors upstream `hermes_time.py` resolution order exactly:
      1. HERMES_TIMEZONE env var
      2. `timezone:` in ~/.hermes/config.yaml
      3. the machine's local timezone (empty string -> caller uses local time)

    Getting this wrong shifts every delivery by the UTC offset: an Ubuntu VPS
    runs on UTC so converting to UTC happened to be correct there, but a macOS
    desktop runs on the user's own timezone.
    """
    tz_env = os.environ.get("HERMES_TIMEZONE", "").strip()
    if tz_env:
        return tz_env
    return hermes_config_timezone(config_path)


def _hermes_tzinfo(config_path: Path | None = None):
    """Resolve `hermes_effective_timezone()` to a tzinfo, falling back to local.

    Fail-open like upstream: an unusable timezone string must not break cron
    reconcile, it just means Hermes is running on machine-local time.
    """
    tz_name = hermes_effective_timezone(config_path)
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.now().astimezone().tzinfo


def local_time_to_cron(
    delivery_time: str,
    tz_name: str,
    offset_minutes: int = 0,
    *,
    config_path: Path | None = None,
) -> str:
    """Convert a topic's local delivery time to a cron expression Hermes reads.

    The returned expression is in Hermes' *effective* timezone, not UTC —
    `hermes cron` evaluates schedules against `hermes_time.now()`.
    """
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", delivery_time.strip())
    if not match:
        raise ValueError("delivery_time must use HH:MM format")

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("delivery_time must be a valid 24-hour time")

    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {tz_name}") from exc

    local_dt = datetime.now(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if offset_minutes:
        local_dt = local_dt + timedelta(minutes=offset_minutes)
    target_dt = local_dt.astimezone(_hermes_tzinfo(config_path))
    return f"{target_dt.minute} {target_dt.hour} * * *"


def find_morning_report_jobs(cron_list_output: str) -> list[tuple[str, str, str]]:
    """Return [(job_id, name, state)] for every job whose name starts with the prefix."""
    jobs: list[tuple[str, str, str]] = []
    current_id: str | None = None
    current_state = ""
    for line in cron_list_output.splitlines():
        job_match = re.match(r"\s+([0-9a-f]{8,})\s+\[([^\]]+)\]", line)
        if job_match:
            current_id = job_match.group(1)
            current_state = job_match.group(2).strip()
            continue
        if current_id and line.strip().startswith("Name:"):
            name = line.split(":", 1)[1].strip()
            if name.startswith(CRON_JOB_PREFIX):
                jobs.append((current_id, name, current_state))
            current_id = None
            current_state = ""
    return jobs


def _run_cron(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


def sync_cron_jobs(
    state_path: Path,
    current_topics: list[dict[str, Any]],
    candidate_topics: list[dict[str, Any]],
    enable_cron: bool = False,
    *,
    list_output: str | None = None,
    run_cron: Any | None = None,
) -> str:
    if run_cron is None:
        run_cron = _run_cron

    current_by_key = {t["topic"].casefold(): t for t in current_topics}
    candidate_by_key = {t["topic"].casefold(): t for t in candidate_topics}
    topics_changed = set(current_by_key) != set(candidate_by_key)
    schedule_changed = any(
        bool(cand.get("delivery_time"))
        and bool(cand.get("timezone"))
        and (
            cand.get("delivery_time") != current_by_key.get(key, {}).get("delivery_time")
            or cand.get("timezone") != current_by_key.get(key, {}).get("timezone")
        )
        for key, cand in candidate_by_key.items()
    )
    if not enable_cron and not topics_changed and not schedule_changed:
        return ""

    if list_output is None:
        if state_path.resolve() != DEFAULT_CONFIG_PATH.resolve():
            return "Cron jobs were not reconciled because --state is not the default config path."
        list_result = run_cron(["hermes", "cron", "list", "--all"])
        if list_result.returncode != 0:
            error = (list_result.stderr or list_result.stdout).strip()
            return f"Cron jobs were not reconciled because `hermes cron list --all` failed: {error}"
        list_output = list_result.stdout

    existing_by_name = {name: (jid, state) for jid, name, state in find_morning_report_jobs(list_output)}
    desired_names = {
        cron_job_name_for_topic(t["topic"])
        for t in candidate_topics
        if t.get("delivery_time") and t.get("timezone")
    }
    messages: list[str] = []

    if enable_cron:
        for t in candidate_topics:
            if not (t.get("delivery_time") and t.get("timezone")):
                continue
            name = cron_job_name_for_topic(t["topic"])
            try:
                schedule = local_time_to_cron(str(t["delivery_time"]), str(t["timezone"]))
            except ValueError as exc:
                messages.append(f"Could not schedule '{t['topic']}': {exc}")
                continue
            if name in existing_by_name:
                jid, _ = existing_by_name[name]
                edit_result = run_cron(["hermes", "cron", "--accept-hooks", "edit", jid, "--schedule", schedule])
                if edit_result.returncode != 0:
                    messages.append(f"Edit failed for '{t['topic']}': {(edit_result.stderr or edit_result.stdout).strip()}")
                else:
                    messages.append(f"Updated schedule for '{t['topic']}' to `{schedule}`.")
            else:
                create_result = run_cron([
                    "hermes", "cron", "--accept-hooks", "create",
                    "--name", name, "--skill", CRON_SKILL, "--deliver", "origin",
                    schedule, cron_prompt_for_topic(t["topic"]),
                ])
                if create_result.returncode != 0:
                    messages.append(f"Create failed for '{t['topic']}': {(create_result.stderr or create_result.stdout).strip()}")
                else:
                    messages.append(f"Created job for '{t['topic']}' with schedule `{schedule}`.")
        for name, (jid, _) in existing_by_name.items():
            is_legacy = name == CRON_JOB_NAME
            is_stale = name.startswith(f"{CRON_JOB_PREFIX} - ") and name not in desired_names
            if is_legacy or is_stale:
                rm_result = run_cron(["hermes", "cron", "--accept-hooks", "remove", jid])
                if rm_result.returncode != 0:
                    messages.append(f"Remove failed for '{name}': {(rm_result.stderr or rm_result.stdout).strip()}")
                else:
                    messages.append(f"Removed stale job '{name}'.")
    else:
        for t in candidate_topics:
            if not (t.get("delivery_time") and t.get("timezone")):
                continue
            key = t["topic"].casefold()
            old = current_by_key.get(key)
            if not old:
                continue
            if t["delivery_time"] == old.get("delivery_time") and t["timezone"] == old.get("timezone"):
                continue
            name = cron_job_name_for_topic(t["topic"])
            if name not in existing_by_name:
                messages.append(f"No existing job for '{t['topic']}' to update; use --enable-cron to create it.")
                continue
            try:
                schedule = local_time_to_cron(str(t["delivery_time"]), str(t["timezone"]))
            except ValueError as exc:
                messages.append(f"Could not schedule '{t['topic']}': {exc}")
                continue
            jid, _ = existing_by_name[name]
            edit_result = run_cron(["hermes", "cron", "--accept-hooks", "edit", jid, "--schedule", schedule])
            if edit_result.returncode != 0:
                messages.append(f"Edit failed for '{t['topic']}': {(edit_result.stderr or edit_result.stdout).strip()}")
            else:
                messages.append(f"Updated schedule for '{t['topic']}' to `{schedule}`.")

    if not messages:
        return "Cron jobs already match the configured topics."
    return " ".join(messages)


def build_cron_control_command(job_id: str, action: str) -> list[str]:
    if action not in {"pause", "resume"}:
        raise ValueError(f"unsupported cron action: {action}")
    return ["hermes", "cron", "--accept-hooks", action, job_id]


def control_cron(
    action: str,
    state_path: Path,
    *,
    list_output: str | None = None,
    run_control: Any | None = None,
) -> dict[str, Any]:
    config_check = check_topic_config(state_path)
    base: dict[str, Any] = {
        "configured": config_check["configured"],
        "available_config": config_check["available_config"],
        "missing_config": config_check["missing_config"],
    }

    if list_output is None:
        if state_path.resolve() != DEFAULT_CONFIG_PATH.resolve():
            base["cron_state"] = "not_default_state"
            base["next_action"] = render_cron_control_output("not_default_state", action)
            return base
        list_result = _run_cron(["hermes", "cron", "list", "--all"])
        if list_result.returncode != 0:
            error = (list_result.stderr or list_result.stdout).strip()
            base["cron_state"] = "error"
            base["next_action"] = render_cron_control_output("error", action, error=error)
            return base
        list_output = list_result.stdout

    jobs = find_morning_report_jobs(list_output)
    if not jobs:
        base["cron_state"] = "no_job"
        base["next_action"] = render_cron_control_output(f"no_job_{action}", action)
        return base

    desired_state = "paused" if action == "pause" else "active"
    acted = 0
    skipped = 0
    errors = 0
    details: list[str] = []
    for jid, name, state in jobs:
        if state == desired_state:
            skipped += 1
            details.append(f"{name}: already {desired_state}")
            continue
        run_result = run_control(jid, action) if run_control is not None else _run_cron(build_cron_control_command(jid, action))
        if run_result.returncode != 0:
            errors += 1
            details.append(f"{name}: failed - {(run_result.stderr or run_result.stdout).strip()}")
        else:
            acted += 1
            details.append(f"{name}: {action}d")

    base["details"] = details
    if errors:
        base["cron_state"] = "error"
        base["next_action"] = render_cron_control_output("error", action, error="; ".join(details))
    elif acted == 0:
        base["cron_state"] = "already_paused" if action == "pause" else "already_running"
        base["next_action"] = render_cron_control_output(base["cron_state"], action)
    else:
        base["cron_state"] = "paused" if action == "pause" else "resumed"
        base["next_action"] = render_cron_control_output(base["cron_state"], action)
    return base


# ── Rendering ──────────────────────────────────────────────────────────
def _missing_section(topics: list[dict[str, Any]], missing_config: dict[str, list[str]]) -> str:
    if not topics:
        return (
            "\nNo topics are configured yet. Ask which topic or topics to track "
            "(give 2-3 relevant examples).\n"
        )
    lines: list[str] = []
    for t in topics:
        miss = missing_config.get(t["topic"])
        if miss:
            lines.append(f"• {t['topic']}: {', '.join(miss)}")
    if not lines:
        return ""
    return (
        "\nAsk only for these missing fields, per topic (one short Telegram-friendly "
        "bullet each, natural suggestions):\n"
        + "\n".join(lines)
        + "\nFor each field, ask naturally: topics -> which topic(s) to track; "
        "delivery_time -> a morning time; timezone -> confirm the timezone; "
        "report_style -> one of concise, deep_analysis, opportunities_risks; "
        "report_language -> which language; audio_summary -> whether to enable audio; "
        "delivery_channel -> whether Telegram is okay.\n"
    )


def render_next_action(
    configured: bool,
    bullets: list[str],
    warnings: list[str],
    topics: list[dict[str, Any]],
    missing_config: dict[str, list[str]],
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
    if bullets:
        requested_section = "\nYou MUST present the following changes as bullets:\n" + "\n".join(bullets) + "\n"
    warnings_section = ""
    if warnings:
        warnings_section = "\nWarnings to tell the user:\n" + "\n".join(warnings) + "\n"
    missing_section = _missing_section(topics, missing_config)
    cron_sync_section = ""
    if cron_sync_message:
        cron_sync_section = f"\nCron sync result: {cron_sync_message}\n"
    return (
        template
        .replace("{requested_config_section}", requested_section)
        .replace("{warnings_section}", warnings_section)
        .replace("{missing_config_section}", missing_section)
        .replace("{cron_sync_section}", cron_sync_section)
    )


def render_cron_control_output(template_name: str, action: str, error: str = "") -> str:
    data = json.loads(OUTPUT_TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = data["steps"]["cron_control"]
    template = templates[template_name]["next_action"]
    return template.replace("{action}", action).replace("{error}", error)


def render_prepare_output(
    state_path: Path,
    requested: dict[str, Any],
    save: bool = False,
    enable_cron: bool = False,
) -> dict[str, Any]:
    current_data = load_config_data(state_path)
    current_check = check_topic_config(current_data)
    candidate_data = apply_requested_config(current_data, requested)
    candidate_check = check_topic_config(candidate_data)
    bullets, warnings = requested_review(current_data, candidate_data, requested)

    cron_sync_message = ""
    if save and candidate_check["configured"]:
        save_config_data(state_path, saved_config_data(candidate_check))
        cron_sync_message = sync_cron_jobs(
            state_path,
            current_check["available_config"]["topics"],
            candidate_check["available_config"]["topics"],
            enable_cron=enable_cron,
        )

    topics = candidate_check["available_config"]["topics"]
    return {
        "configured": candidate_check["configured"],
        "available_config": candidate_check["available_config"],
        "missing_config": candidate_check["missing_config"],
        "requested_changes": bullets,
        "warnings": warnings,
        "next_action": render_next_action(
            candidate_check["configured"],
            bullets,
            warnings,
            topics,
            candidate_check["missing_config"],
            save,
            cron_sync_message,
        ),
    }


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Morning Report config setup/update (per-topic)")
    parser.add_argument("--state", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--enable-cron", action="store_true")
    parser.add_argument("--pause-cron", dest="pause_cron", action="store_true", help="Pause all Morning Report cron jobs.")
    parser.add_argument("--resume-cron", dest="resume_cron", action="store_true", help="Resume all Morning Report cron jobs.")
    parser.add_argument("--topic", help="Topic to change (selector for field changes).")
    parser.add_argument("--all-topics", dest="all_topics", action="store_true", help="Apply field changes to every topic.")
    parser.add_argument("--add-topic", dest="add_topic", action="append", help="Add a new topic config (inherits defaults).")
    parser.add_argument("--remove-topic", dest="remove_topic", action="append", help="Remove a topic config and its cron job.")
    parser.add_argument("--delivery-time", dest="delivery_time")
    parser.add_argument("--timezone")
    parser.add_argument("--report-style", dest="report_style")
    parser.add_argument("--report-language", dest="report_language")
    parser.add_argument("--audio-summary", dest="audio_summary")
    parser.add_argument("--delivery-channel", dest="delivery_channel")
    args = parser.parse_args()
    state_path = Path(args.state)

    if args.pause_cron and args.resume_cron:
        print(
            json.dumps(
                {"success": False, "error": "--pause-cron and --resume-cron are mutually exclusive"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    if args.pause_cron or args.resume_cron:
        action = "pause" if args.pause_cron else "resume"
        print(json.dumps(control_cron(action, state_path), ensure_ascii=False, separators=(",", ":")))
        return 0

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
