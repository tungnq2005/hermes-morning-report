"""History manifest helpers for Morning Report runs."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_FILE = "manifest.json"
REPORT_FILE = "report.md"
AUDIO_FILE = "morning-report.mp3"


def _timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_manifest(run_dir: Path) -> dict[str, Any]:
    return {
        "run_id": run_dir.name,
        "created_at": _timestamp(),
        "report": {
            "status": "pending",
            "file": None,
            "validation_attempts": 0,
        },
        "audio": {
            "status": "disabled",
            "file": None,
        },
    }


def load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / MANIFEST_FILE
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return _base_manifest(run_dir)


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_into_run_dir(source: Path, run_dir: Path, filename: str) -> Path:
    target = run_dir / filename
    run_dir.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return target


def _short_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _next_attempt(existing: Any) -> int:
    if not isinstance(existing, dict):
        return 1
    try:
        return int(existing.get("validation_attempts", 0)) + 1
    except (TypeError, ValueError):
        return 1


def _ensure_manifest_defaults(manifest: dict[str, Any], run_dir: Path) -> None:
    manifest.setdefault("run_id", run_dir.name)
    manifest.setdefault("created_at", _timestamp())
    manifest.pop("sources", None)
    manifest.setdefault(
        "audio",
        {
            "status": "disabled",
            "file": None,
        },
    )


def record_report_validation(run_dir: Path, report_file: Path, ok: bool) -> dict[str, Any]:
    report_path = _copy_into_run_dir(report_file, run_dir, REPORT_FILE)
    report_text = report_path.read_text(encoding="utf-8")
    manifest = load_manifest(run_dir)
    _ensure_manifest_defaults(manifest, run_dir)

    manifest["report"] = {
        "status": "validated" if ok else "validation_failed",
        "file": REPORT_FILE,
        "validation_attempts": _next_attempt(manifest.get("report")),
        "char_count": len(report_text),
        "sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest()[:12],
    }
    write_manifest(run_dir, manifest)
    return manifest["report"]


def record_audio_validation(run_dir: Path, audio_file: Path) -> dict[str, Any]:
    audio_path = _copy_into_run_dir(audio_file, run_dir, AUDIO_FILE)
    manifest = load_manifest(run_dir)
    _ensure_manifest_defaults(manifest, run_dir)
    manifest.setdefault(
        "report",
        {
            "status": "pending",
            "file": None,
            "validation_attempts": 0,
        },
    )

    existing_audio = manifest.get("audio")
    audio_meta: dict[str, Any] = {
        "status": "validated",
        "file": AUDIO_FILE,
        "bytes": audio_path.stat().st_size,
        "sha256": _short_sha256(audio_path),
    }
    if isinstance(existing_audio, dict) and "validation_attempts" in existing_audio:
        audio_meta["validation_attempts"] = existing_audio["validation_attempts"]

    manifest["audio"] = audio_meta
    write_manifest(run_dir, manifest)
    return manifest["audio"]
