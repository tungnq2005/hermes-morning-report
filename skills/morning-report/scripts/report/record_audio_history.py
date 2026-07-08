"""Update unified Morning Report history after audio delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report.audit_events import append_report_audit_event  # noqa: E402
from report.common import load_run_state, save_run_state  # noqa: E402


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


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_if_present(src: Path | None, dest: Path) -> str | None:
    if src is None:
        return None
    if not src.exists():
        raise FileNotFoundError(f"missing file: {src}")
    if src.resolve(strict=False) != dest.resolve(strict=False):
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return str(dest)


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


def history_paths(state: dict[str, Any], history_dir: Path) -> tuple[Path, Path]:
    run_dir_raw = state.get("history", {}).get("run_dir") or state.get("report_history", {}).get("run_dir")
    if not run_dir_raw:
        raise FileNotFoundError("missing unified history run_dir in run state")
    run_dir = Path(run_dir_raw)
    if not run_dir.exists():
        raise FileNotFoundError(f"missing unified history run_dir: {run_dir}")
    if not run_dir.is_relative_to(history_dir.resolve(strict=False)) and not run_dir.is_absolute():
        run_dir = history_dir / run_dir
    manifest_path = Path(state.get("history", {}).get("manifest_path") or run_dir / "manifest.json")
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing unified history manifest: {manifest_path}")
    return run_dir, manifest_path


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

    run_dir, manifest_path = history_paths(state, Path(args.history_dir))
    manifest = load_json(manifest_path)

    local_audio_script = copy_if_present(audio_script_file, run_dir / "audio-script.txt")
    local_audio_file = copy_if_present(audio_file, run_dir / "morning-report.mp3") if audio_file else None
    generation_manifest = load_optional_json(audio_manifest_path)
    if audio_manifest_path:
        copy_if_present(Path(audio_manifest_path), run_dir / "audio-manifest.json")

    manifest["updated_at"] = now.isoformat()
    manifest["audio"] = {
        "status": audio_status,
        "file": local_audio_file,
        "file_exists": bool(local_audio_file and Path(local_audio_file).exists()),
        "file_bytes": Path(local_audio_file).stat().st_size if local_audio_file and Path(local_audio_file).exists() else None,
        "sha256": sha256_file(Path(local_audio_file)) if local_audio_file else None,
        "script_file": local_audio_script,
        "manifest_file": str(run_dir / "audio-manifest.json") if (run_dir / "audio-manifest.json").exists() else None,
        "generation": generation_manifest,
        "error": audio.get("error"),
    }
    delivery = manifest.setdefault("delivery", {})
    delivery["audio_send_status"] = args.send_status

    audit_record = append_report_audit_event(
        "audio_history_recorded",
        by="record_audio_history.py",
        log_path=Path(args.audit_log),
        details={
            "run_dir": str(run_dir),
            "audio_status": audio_status,
            "send_status": args.send_status,
            "audio_file": local_audio_file,
        },
    )
    manifest["audit_record"] = audit_record
    write_json(manifest_path, manifest)

    state["history"] = {
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
    }
    state["success"] = True
    state["phase"] = "complete"
    state["can_continue"] = False
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
        "history": state["history"],
        "audio_history": manifest,
        "next_action": state["next_action"],
    }
