"""Shared setup helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

SETUP_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SETUP_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
WORKSPACE = SKILL_DIR.parent.parent

DEFAULT_STATE = SKILL_DIR / "state" / "current-topics.md"
DEFAULT_USER = WORKSPACE / "USER.md"
DEFAULT_AGENTS = WORKSPACE / "AGENTS.md"


def command_result(cmd: list[str], timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        ok = completed.returncode == 0
        result: dict[str, Any] = {
            "ok": ok,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip()[:1000],
            "stderr": completed.stderr.strip()[:1000],
        }
        if not ok:
            result["error"] = "Command returned a non-zero exit code."
        return result
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"timeout after {timeout}s",
        }


def command_json_result(cmd: list[str], timeout: int) -> dict[str, Any]:
    result = command_result(cmd, timeout)
    if result.get("stdout"):
        try:
            result["json"] = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            result["json_error"] = str(exc)
    return result
