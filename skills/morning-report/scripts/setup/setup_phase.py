"""Setup phase helpers that return agent-facing JSON from setup logs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SETUP_LOGS = Path(__file__).with_name("setup_logs.json")

from setup.system_readiness import check_cron_help, check_openclaw  # noqa: E402


def load_setup_logs(path: Path = SETUP_LOGS) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"setup logs must be a JSON object: {path}")
    return data


def setup_log(name: str, *, logs_path: Path = SETUP_LOGS) -> dict[str, Any]:
    logs = load_setup_logs(logs_path)
    value = logs[name]
    if not isinstance(value, dict):
        raise ValueError(f"setup log must be a JSON object: {name}")
    return value


def check_openclaw_failure_output(timeout: int = 10) -> dict[str, Any] | None:
    result = check_openclaw(timeout)
    if result.get("ok"):
        return None
    return setup_log("openclaw_cli_unavailable")


def check_cron_help_failure_output(timeout: int = 10) -> dict[str, Any] | None:
    result = check_cron_help(timeout)
    if result.get("ok"):
        return None
    return setup_log("cron_cli_unavailable")
