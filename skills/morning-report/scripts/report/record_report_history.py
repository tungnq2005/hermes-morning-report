#!/usr/bin/env python3
"""Record a Morning Report run into report history."""

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
DEFAULT_HISTORY_DIR = SKILL_DIR / "state" / "report-history"
DEFAULT_AUDIO_HISTORY_DIR = SKILL_DIR / "state" / "audio-history"
DEFAULT_AUDIT_LOG = SKILL_DIR / "state" / "audit.log"
DEFAULT_STATE = SKILL_DIR / "state" / "current-topics.md"
DEFAULT_USER = SKILL_DIR.parent.parent / "USER.md"

sys.path.insert(0, str(SCRIPTS_DIR))
from report.audit_events import append_report_audit_event  # noqa: E402
from config_status import build_status  # noqa: E402


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def copy_if_present(src: Path | None, dest: Path) -> str | None:
    if src is None:
        return None
    if not src.exists():
        raise FileNotFoundError(f"missing file: {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return str(dest)


def load_json_file(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"missing file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def resolved_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def manifest_matches_audio(manifest: dict[str, Any], audio_file: Path) -> bool:
    target = resolved_path(audio_file)
    for key in ("output", "history_audio"):
        value = manifest.get(key)
        if isinstance(value, str) and resolved_path(value) == target:
            return True
    return False


def find_audio_manifest(audio_file: Path | None, audio_history_dir: Path) -> tuple[dict[str, Any], Path] | None:
    if audio_file is None or not audio_history_dir.exists():
        return None

    manifests = sorted(
        audio_history_dir.glob("*/*/manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests:
        try:
            manifest = load_json_file(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if manifest is None or manifest.get("success") is not True:
            continue
        if manifest_matches_audio(manifest, audio_file):
            return manifest, manifest_path
    return None


def make_run_dir(history_dir: Path, report_text: str, now: datetime) -> Path:
    digest = hashlib.sha256(report_text.encode("utf-8")).hexdigest()[:8]
    date_dir = history_dir / now.strftime("%Y-%m-%d")
    base_name = f"{now.strftime('%H%M%S')}-{digest}"
    candidate = date_dir / base_name
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = date_dir / f"{base_name}-{suffix}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def parse_json_arg(raw: str | None, label: str) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON") from exc


def extract_report_urls(report_file: Path) -> list[str]:
    text = report_file.read_text(encoding="utf-8") if report_file.exists() else ""
    urls: list[str] = []
    seen: set[str] = set()
    marker = "]("
    for part in text.split(marker)[1:]:
        url = part.split(")", 1)[0].strip()
        if url.startswith("http") and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def record_report_phase(args: argparse.Namespace) -> dict[str, Any]:
    from report.common import load_run_state, read_json, run_subprocess_json, runner_command, save_run_state, state_path

    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    report_file = Path(args.report_file or state["report_file"])
    source_manifest = read_json(Path(state["source_collection"]["manifest_path"]))
    audio_enabled = bool(state["config"].get("audio_enabled"))
    audio_status = args.audio_status or ("pending" if audio_enabled else "disabled")
    extra = {
        "history_scope": "report_sent",
        "run_state_file": str(state_path(work_dir)),
        "source_manifest": state["source_collection"]["manifest_path"],
        "source_collection": {
            "source_count": source_manifest.get("source_count", 0),
            "fresh_24h_count": source_manifest.get("fresh_24h_count", 0),
        },
    }
    cmd = [
        sys.executable,
        str(Path(__file__)),
        "--report-file",
        str(report_file),
        "--history-dir",
        str(Path(args.history_dir)),
        "--audio-history-dir",
        str(Path(args.audio_history_dir)),
        "--audit-log",
        str(Path(args.audit_log)),
        "--state",
        str(Path(args.state)),
        "--user",
        str(Path(args.user)),
        "--send-status",
        args.send_status,
        "--audio-status",
        audio_status,
        "--extra",
        json.dumps(extra, ensure_ascii=False),
    ]
    for url in extract_report_urls(report_file):
        cmd.extend(["--source-url", url])
    for url in source_manifest.get("failed_fetch_urls", []):
        cmd.extend(["--failed-url", url])

    code, manifest, error = run_subprocess_json(cmd)
    record = manifest if code == 0 and manifest else {"success": False, "error": error}
    state["report_history"] = record
    next_action_type = "write_audio_script" if record.get("success") and audio_enabled else ("done" if record.get("success") else "record_failed")
    state["next_action"] = {
        "type": next_action_type,
        "message_goal": (
            "Write the audio script next."
            if record.get("success") and audio_enabled
            else (
                "No extra customer-facing recap is needed."
                if record.get("success")
                else "Do not change the sent report; mention report history recording failed only if asked."
            )
        ),
    }
    if next_action_type == "write_audio_script":
        state["next_action"]["audio_script_file"] = state["audio_script_file"]
        state["next_action"]["next_command"] = runner_command("validate-audio", work_dir)
    save_run_state(work_dir, state)
    return {
        "success": bool(record.get("success")),
        "phase": "record-report",
        "can_continue": bool(record.get("success") and audio_enabled),
        "work_dir": str(work_dir),
        "report_file": str(report_file),
        "audio_script_file": state.get("audio_script_file"),
        "config": state["config"],
        "report_history": record,
        "next_action": state["next_action"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a Morning Report run")
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--audio-history-dir", default=str(DEFAULT_AUDIO_HISTORY_DIR))
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--user", default=str(DEFAULT_USER))
    parser.add_argument("--audio-script-file")
    parser.add_argument("--audio-file")
    parser.add_argument("--audio-manifest")
    parser.add_argument("--audio-status", default="not_requested")
    parser.add_argument("--send-status", default="not_recorded")
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--failed-url", action="append", default=[])
    parser.add_argument("--extra", help="Optional JSON object merged into manifest.extra")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    now = utc_now()

    try:
        report_path = Path(args.report_file)
        report_text = read_text_file(report_path)
        if not report_text.strip():
            raise ValueError("report file is empty")

        state_status = build_status(Path(args.state), Path(args.user))
        prefs = state_status.get("state", {}).get("report_preferences", {})

        if args.dry_run:
            preview = {
                "success": True,
                "dry_run": True,
                "created_at": now.isoformat(),
                "planned_history_dir": str(Path(args.history_dir)),
                "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
                "report_char_count": len(report_text),
                "topics": state_status.get("state", {}).get("active_topics", []),
                "optional_topics": state_status.get("state", {}).get("optional_topics", []),
                "report_preferences": prefs,
                "delivery_channel": prefs.get("Delivery channel", ""),
                "send_status": args.send_status,
                "audio_status": args.audio_status,
                "source_urls": args.source_url,
                "failed_urls": args.failed_url,
                "source_count": len(args.source_url),
                "failed_url_count": len(args.failed_url),
                "config_status": state_status,
                "extra": parse_json_arg(args.extra, "--extra") or {},
            }
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return 0

        run_dir = make_run_dir(Path(args.history_dir), report_text, now)
        local_report = run_dir / "report.md"
        local_report.write_text(report_text, encoding="utf-8")

        audio_script_path = copy_if_present(
            Path(args.audio_script_file) if args.audio_script_file else None,
            run_dir / "audio-script.txt",
        )
        audio_file_path = copy_if_present(
            Path(args.audio_file) if args.audio_file else None,
            run_dir / "morning-report.mp3",
        )
        audio_file_arg = Path(args.audio_file) if args.audio_file else None
        audio_manifest_source: str | None = None
        audio_manifest = load_json_file(Path(args.audio_manifest) if args.audio_manifest else None)
        if args.audio_manifest:
            audio_manifest_source = str(Path(args.audio_manifest))
        elif args.audio_status == "generated":
            inferred = find_audio_manifest(audio_file_arg, Path(args.audio_history_dir))
            if inferred is not None:
                audio_manifest, inferred_path = inferred
                audio_manifest_source = str(inferred_path)
        if audio_manifest is not None:
            (run_dir / "audio-manifest.json").write_text(
                json.dumps(audio_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        extra = parse_json_arg(args.extra, "--extra") or {}
        if not isinstance(extra, dict):
            raise ValueError("--extra must be a JSON object")

        manifest = {
            "success": True,
            "created_at": now.isoformat(),
            "run_dir": str(run_dir),
            "report_file": str(local_report),
            "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
            "report_char_count": len(report_text),
            "topics": state_status.get("state", {}).get("active_topics", []),
            "optional_topics": state_status.get("state", {}).get("optional_topics", []),
            "report_preferences": prefs,
            "delivery_channel": prefs.get("Delivery channel", ""),
            "send_status": args.send_status,
            "audio_status": args.audio_status,
            "audio_script_file": audio_script_path,
            "audio_file": audio_file_path,
            "audio_manifest_file": str(run_dir / "audio-manifest.json") if audio_manifest is not None else None,
            "audio_manifest_source_file": audio_manifest_source,
            "source_urls": args.source_url,
            "failed_urls": args.failed_url,
            "source_count": len(args.source_url),
            "failed_url_count": len(args.failed_url),
            "config_status": state_status,
            "extra": extra,
        }
        audit_record = append_report_audit_event(
            "report_recorded",
            by="record_report_history.py",
            log_path=Path(args.audit_log),
            details={
                "run_dir": str(run_dir),
                "topics": manifest["topics"],
                "audio_status": args.audio_status,
                "send_status": args.send_status,
                "source_count": len(args.source_url),
                "failed_url_count": len(args.failed_url),
            },
        )
        manifest["audit_record"] = audit_record
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"record_report_history.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
