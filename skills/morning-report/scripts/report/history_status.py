#!/usr/bin/env python3
"""Show latest unified Morning Report history and audit events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
DEFAULT_HISTORY = SKILL_DIR / "state" / "history"
DEFAULT_AUDIT_LOG = SKILL_DIR / "state" / "audit.log"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_manifests(root: Path, limit: int) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    paths = sorted(root.rglob("manifest.json"), key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    results = []
    for path in paths[:limit]:
        try:
            data = load_json(path)
        except Exception as exc:
            data = {"success": False, "error": f"failed to read manifest: {exc}"}
        data["manifest_path"] = str(path)
        results.append(data)
    return results


def audit_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"parse_error": True, "line": line})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Morning Report history status")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG))
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    limit = max(1, args.limit)
    result = {
        "history": latest_manifests(Path(args.history), limit),
        "audit_tail": audit_tail(Path(args.audit_log), limit),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
