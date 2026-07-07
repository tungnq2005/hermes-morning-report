"""Record audio history after Telegram media/notice send succeeds."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report.audit_events import append_report_audit_event  # noqa: E402
from report.common import load_run_state, save_run_state, state_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_sent_dir(history_dir: Path, status: str, now: datetime) -> Path:
    date_dir = history_dir / "sent" / now.strftime("%Y-%m-%d")
    base = f"{now.strftime('%H%M%S')}-{status}"
    candidate = date_dir / base
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = date_dir / f"{base}-{suffix}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def load_optional_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        return None
    data = json.loads(source.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def inferred_audio_status(state: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    audio_status = state.get("audio", {}).get("status", "")
    if audio_status == "generated":
        return "sent"
    if audio_status in {"failed", "disabled"}:
        return audio_status
    return "not_recorded"


def record_audio_phase(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    now = utc_now()
    audio = state.get("audio", {})
    audio_status = inferred_audio_status(state, args.audio_status)
    audio_file = Path(args.audio_file or audio.get("file", "")) if (args.audio_file or audio.get("file")) else None
    audio_script_file = Path(args.audio_script_file or audio.get("script_file", "")) if (args.audio_script_file or audio.get("script_file")) else None
    audio_manifest_path = args.audio_manifest or audio.get("manifest")

    if audio_status == "sent" and (audio_file is None or not audio_file.exists()):
        raise FileNotFoundError("audio_status is sent but audio file is missing")

    run_dir = make_sent_dir(Path(args.audio_history_dir), audio_status, now)
    generation_manifest = load_optional_json(audio_manifest_path)
    manifest = {
        "success": True,
        "created_at": now.isoformat(),
        "run_dir": str(run_dir),
        "history_scope": "audio_sent",
        "audio_status": audio_status,
        "send_status": args.send_status,
        "audio_file": str(audio_file) if audio_file else None,
        "audio_file_exists": bool(audio_file and audio_file.exists()),
        "audio_file_bytes": audio_file.stat().st_size if audio_file and audio_file.exists() else None,
        "audio_sha256": sha256_file(audio_file) if audio_file else None,
        "audio_script_file": str(audio_script_file) if audio_script_file else None,
        "audio_manifest_source_file": audio_manifest_path,
        "generation_manifest": generation_manifest,
        "report_history_file": state.get("report_history", {}).get("manifest_path")
        or state.get("report_history", {}).get("run_dir"),
        "run_state_file": str(state_path(work_dir)),
        "config": state.get("config", {}),
    }
    audit_record = append_report_audit_event(
        "audio_history_recorded",
        by="record_audio_history.py",
        log_path=Path(args.audit_log),
        details={
            "run_dir": str(run_dir),
            "audio_status": audio_status,
            "send_status": args.send_status,
            "audio_file": str(audio_file) if audio_file else None,
        },
    )
    manifest["audit_record"] = audit_record
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    state["audio_history"] = manifest
    state["next_action"] = {
        "type": "done",
        "message_goal": "No extra customer-facing recap is needed.",
    }
    save_run_state(work_dir, state)
    return {
        "success": True,
        "phase": "record-audio",
        "can_continue": False,
        "work_dir": str(work_dir),
        "config": state.get("config", {}),
        "audio": audio,
        "audio_history": manifest,
        "next_action": state["next_action"],
    }
