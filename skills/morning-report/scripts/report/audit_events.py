"""Append Morning Report report/audio audit events as JSONL."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
DEFAULT_AUDIT_LOG = SKILL_DIR / "state" / "audit.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_report_audit_event(
    action: str,
    *,
    details: dict[str, Any] | None = None,
    by: str = "report",
    log_path: Path = DEFAULT_AUDIT_LOG,
) -> dict[str, Any]:
    record = {
        "ts": utc_now(),
        "action": action,
        "by": by,
        "details": details or {},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
