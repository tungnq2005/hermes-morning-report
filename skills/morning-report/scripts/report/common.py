"""Shared helpers for Morning Report run phases."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
WORKSPACE = SKILL_DIR.parent.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from config_status import DEFAULT_STATE, DEFAULT_USER, build_status  # noqa: E402

DEFAULT_WORK_DIR = Path("/tmp/morning-report-run")
DEFAULT_REPORT_FILE = Path("/tmp/morning-report.md")
DEFAULT_AUDIO_SCRIPT_FILE = Path("/tmp/morning-report-audio.txt")
DEFAULT_AUDIO_FILE = SKILL_DIR / "state" / "morning-report.mp3"
DEFAULT_TARGET_FETCHED = 5
RUNNER_SCRIPT = "skills/morning-report/scripts/report/run.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def state_path(work_dir: Path) -> Path:
    return work_dir / "run-state.json"


def load_run_state(work_dir: Path) -> dict[str, Any]:
    path = state_path(work_dir)
    if not path.exists():
        raise FileNotFoundError(f"missing run state: {path}")
    return read_json(path)


def save_run_state(work_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path(work_dir), state)


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "success",
        "phase",
        "can_continue",
        "work_dir",
        "report_file",
        "audio_script_file",
        "audio_file",
        "config",
        "search_collection",
        "source_collection",
        "validation",
        "report_output",
        "audio",
        "history",
        "report_history",
        "audio_history",
        "next_action",
    ]
    return {key: result[key] for key in keep if key in result}


def print_result(result: dict[str, Any], *, agent: bool, compact: bool) -> None:
    if agent or compact:
        result = compact_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=None if compact else 2))


def run_subprocess_json(cmd: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
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


def runner_command(phase: str, work_dir: Path | str, *extra: str) -> str:
    parts = ["python3", RUNNER_SCRIPT, phase, "--agent", "--work-dir", str(work_dir), *extra]
    return " ".join(shlex.quote(str(part)) for part in parts)


def pref_value(status: dict[str, Any], key: str) -> str:
    return status.get("state", {}).get("report_preferences", {}).get(key, "")


def canonical_style(status: dict[str, Any]) -> str:
    style = status.get("state", {}).get("report_style", {})
    return str(style.get("canonical") or pref_value(status, "Report style")).strip()


def enabled(value: str) -> bool:
    return value.strip().lower() in {"enabled", "enable", "true", "yes", "on", "1"}


def configured_topics(status: dict[str, Any]) -> list[str]:
    return list(status.get("state", {}).get("active_topics", []))


def query_topic(topics: list[str]) -> str:
    return "; ".join(topic.strip() for topic in topics if topic.strip())


def config_from_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "topics": configured_topics(status),
        "delivery_time": pref_value(status, "Delivery time"),
        "timezone": pref_value(status, "Timezone"),
        "report_style": canonical_style(status),
        "report_language": pref_value(status, "Report language"),
        "audio_summary": pref_value(status, "Audio summary"),
        "audio_enabled": enabled(pref_value(status, "Audio summary")),
        "delivery_channel": pref_value(status, "Delivery channel"),
    }


def stop_result(
    *,
    phase: str,
    work_dir: Path,
    reason: str,
    message_goal: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "success": False,
        "phase": phase,
        "can_continue": False,
        "work_dir": str(work_dir),
        "next_action": {
            "type": "stop",
            "reason": reason,
            "message_goal": message_goal,
        },
    }
    if extra:
        result.update(extra)
    save_run_state(work_dir, result)
    return result


def ensure_runnable_config(args: Any, work_dir: Path, phase: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    status = build_status(Path(args.state), Path(args.user))
    setup_status = status.get("state", {}).get("setup_status", "")
    if setup_status in {"paused", "disabled"}:
        return status, stop_result(
            phase=phase,
            work_dir=work_dir,
            reason=f"morning_report_{setup_status}",
            message_goal="Tell the user Morning Report is not active and no report was generated.",
            extra={"config_status": status},
        )
    if not status.get("configured"):
        return status, stop_result(
            phase=phase,
            work_dir=work_dir,
            reason="config_not_ready",
            message_goal="Tell the user Morning Report setup is incomplete and no report was generated.",
            extra={
                "missing_required": status.get("missing_required", []),
                "config_status": status,
            },
        )
    return status, None
