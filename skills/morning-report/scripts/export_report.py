#!/usr/bin/env python3
"""Export a stored Morning Report run to Google Docs / Slides / PDF via doc-convert.

Morning Report writes report.md into a run directory and then forgets about it, while
doc-convert turns a file into a Google deliverable but expects someone to hand it a
file. This script is the seam between the two: it resolves what the user means by
"today's report" or "the crypto one" to a run directory in history, then runs
doc-convert's convert.py on that run's report.md.

That is what makes the Google copy available at ANY time -- not only inside the single
turn that produced the report, which is all the agent could do while the run directory
lived nowhere but in its own context.

Usage:
  export_report.py --list [--limit 10]
  export_report.py [--latest | --topic "AI" | --date 2026-08-19 | --run-dir PATH] \
      [--to gdoc|gslides|pdf|docx|md] [--title "..."] [--again] \
      [--image-query "gold bars" --image-query "federal reserve building"]

Prints one JSON object with next_action.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from helpers.history import find_export, load_manifest, record_export

# .absolute() (not .resolve()) so the ~/.hermes invocation path survives: MEDIA
# delivery rejects paths outside the workspace, and resolve() would rewrite them
# to the repo checkout the skill is symlinked from.
SCRIPT_DIR = Path(__file__).absolute().parent
SKILL_DIR = SCRIPT_DIR.parent
HISTORY_DIR = SKILL_DIR / "state" / "history"
OUTPUT_TEMPLATES_PATH = SKILL_DIR / "references" / "workflow-output-templates.json"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

TARGETS = ("gdoc", "gslides", "pdf", "docx", "md")
DEFAULT_TARGET = "gdoc"
CONVERT_TIMEOUT_SECONDS = 600
REPORT_FILE = "report.md"


# -- doc-convert discovery ---------------------------------------------
def find_convert_script() -> Path | None:
    """Locate doc-convert's convert.py across the installed and repo layouts.

    Installed, Morning Report sits at ~/.hermes/skills/productivity/morning-report
    while doc-convert sits at ~/.hermes/skills/doc-convert; in the repo both are
    siblings under skills/. Try both rather than hard-coding one.
    """
    env_dir = os.environ.get("DOC_CONVERT_DIR")
    candidates: list[Path] = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates += [
        SKILL_DIR.parent.parent / "doc-convert",   # installed: skills/productivity/.. -> skills/
        SKILL_DIR.parent / "doc-convert",          # repo: skills/
        HERMES_HOME / "skills" / "doc-convert",
    ]
    for base in candidates:
        script = base / "scripts" / "convert.py"
        if script.exists():
            return script
    return None


# -- History reading ---------------------------------------------------
def report_title(report_path: Path) -> str:
    try:
        for line in report_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
    return ""


def describe_run(run_dir: Path) -> dict[str, Any]:
    manifest = load_manifest(run_dir)
    report_path = run_dir / REPORT_FILE
    has_report = report_path.exists()
    title = str(manifest.get("title") or "").strip()
    if not title and has_report:
        title = report_title(report_path)
    run_id = run_dir.name
    time_text = ""
    if len(run_id) >= 6 and run_id[:6].isdigit():
        time_text = f"{run_id[0:2]}:{run_id[2:4]}"
    report_meta = manifest.get("report")
    exports = manifest.get("exports")
    return {
        "run_dir": str(run_dir),
        "run_id": run_id,
        "date": run_dir.parent.name,
        "time": time_text,
        "topic": str(manifest.get("topic") or "").strip(),
        "title": title,
        "has_report": has_report,
        "report_status": report_meta.get("status") if isinstance(report_meta, dict) else None,
        "exports": exports if isinstance(exports, list) else [],
    }


def list_runs(history_dir: Path, *, only_with_report: bool = True) -> list[dict[str, Any]]:
    """Newest first. Directory names are date/HHMMSS, so name sort == time sort."""
    if not history_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for day_dir in sorted((p for p in history_dir.iterdir() if p.is_dir()), reverse=True):
        for run_dir in sorted((p for p in day_dir.iterdir() if p.is_dir()), reverse=True):
            info = describe_run(run_dir)
            if only_with_report and not info["has_report"]:
                continue
            runs.append(info)
    return runs


def _matches_topic(run: dict[str, Any], wanted: str) -> bool:
    needle = wanted.casefold().strip()
    if not needle:
        return False
    haystacks = [str(run.get("topic") or ""), str(run.get("title") or "")]
    return any(needle in h.casefold() for h in haystacks)


def resolve_run(
    runs: list[dict[str, Any]],
    *,
    topic: str = "",
    date: str = "",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Return (chosen run, candidates considered). Newest match wins."""
    candidates = runs
    if date:
        candidates = [r for r in candidates if r["date"] == date]
    if topic:
        candidates = [r for r in candidates if _matches_topic(r, topic)]
    return (candidates[0] if candidates else None), candidates


# -- Rendering ---------------------------------------------------------
def render_next_action(template_name: str, **fields: Any) -> str:
    data = json.loads(OUTPUT_TEMPLATES_PATH.read_text(encoding="utf-8"))
    template = data["steps"]["export_report"][template_name]["next_action"]
    for key, value in fields.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- Export ------------------------------------------------------------
def classify_failure(manifest: dict[str, Any]) -> str:
    """Tell 'Google is not connected' apart from a genuine conversion failure."""
    error = str(manifest.get("error") or "")
    warnings = [str(w) for w in manifest.get("warnings", [])]
    # doc-convert reports this in either language depending on where it failed.
    if re.search(r"authorize|unauthorized|token|chưa kết nối google", error, re.IGNORECASE):
        return "google_unauthorized"
    if any(w.startswith("google_unauthorized") for w in warnings):
        return "google_unauthorized"
    return "convert_failed"


def run_convert(
    convert_script: Path,
    report_path: Path,
    target: str,
    title: str,
    image_queries: list[str] | None = None,
    no_auto_images: bool = False,
) -> dict[str, Any]:
    cmd = [sys.executable, str(convert_script), "--input", str(report_path), "--to", target]
    if title:
        cmd += ["--title", title]
    # One English query per section, in section order: Openverse indexes almost
    # nothing under Vietnamese, so a report written in Vietnamese gets no pictures
    # at all unless the agent translates its section titles first.
    for query in image_queries or []:
        cmd += ["--image-query", query]
    if no_auto_images:
        cmd.append("--no-auto-images")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CONVERT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "doc-convert timed out"}
    stdout = (proc.stdout or "").strip()
    if stdout:
        start, end = stdout.find("{"), stdout.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(stdout[start:end + 1])
            except json.JSONDecodeError:
                pass
    fallback = (proc.stderr or stdout or "doc-convert produced no output").strip()
    return {"success": False, "error": fallback[:500]}


def export_run(
    run: dict[str, Any],
    *,
    target: str,
    title: str = "",
    again: bool = False,
    convert_script: Path | None = None,
    image_queries: list[str] | None = None,
    no_auto_images: bool = False,
) -> dict[str, Any]:
    run_dir = Path(run["run_dir"])
    report_path = run_dir / REPORT_FILE
    base: dict[str, Any] = {
        "success": False,
        "run_dir": str(run_dir),
        "topic": run.get("topic", ""),
        "date": run.get("date", ""),
        "target": target,
    }

    if not report_path.exists():
        base["error"] = "report_missing"
        base["next_action"] = render_next_action("failed", error="the stored run has no report.md")
        return base

    queries = list(image_queries or [])
    manifest = load_manifest(run_dir)
    if not again:
        existing = find_export(manifest, target)
        # Different pictures means a different document: reuse only covers asking
        # for the same thing twice, not asking for it illustrated differently.
        if existing and list(existing.get("image_queries") or []) != queries:
            existing = None
        if existing:
            base.update({
                "success": True,
                "reused": True,
                "google_url": existing.get("google_url", ""),
                "output": existing.get("output", ""),
                "title": existing.get("title", run.get("title", "")),
                "exported_at": existing.get("at", ""),
                "next_action": render_next_action("reused", exported_at=existing.get("at", "")),
            })
            return base

    convert_script = convert_script or find_convert_script()
    if convert_script is None:
        base["error"] = "doc_convert_not_found"
        base["next_action"] = render_next_action(
            "failed", error="the document conversion skill is not installed next to Morning Report")
        return base

    chosen_title = title or run.get("title") or f"Morning Report - {run.get('topic') or run.get('date')}"
    result = run_convert(convert_script, report_path, target, chosen_title,
                         image_queries=queries, no_auto_images=no_auto_images)

    if not result.get("success"):
        reason = classify_failure(result)
        base["error"] = result.get("error", reason)
        base["next_action"] = (
            render_next_action("google_unauthorized") if reason == "google_unauthorized"
            else render_next_action("failed", error=base["error"])
        )
        return base

    # A local render means Google is not connected: the file exists, but it is not the
    # deliverable the user asked for, so say so instead of shipping it silently.
    if target in ("gdoc", "gslides") and result.get("render_engine") != "google":
        base["error"] = "rendered_locally"
        base["output"] = result.get("output", "")
        base["next_action"] = render_next_action("google_unauthorized")
        return base

    export_record = {
        "target": target,
        "title": result.get("title", chosen_title),
        "google_url": result.get("google_url", ""),
        "output": result.get("output", ""),
        "doc_convert_run_dir": result.get("run_dir", ""),
        "image_queries": queries,
        "images_used": result.get("images_used", 0),
        "at": _timestamp(),
    }
    record_export(run_dir, export_record)

    base.update({
        "success": True,
        "reused": False,
        "google_url": export_record["google_url"],
        "output": export_record["output"],
        "title": export_record["title"],
        "exported_at": export_record["at"],
        "images_used": export_record["images_used"],
        "warnings": result.get("warnings", []),
        # md/docx/pdf come back as a file with no link, so the agent must not be told
        # to send a google_url that does not exist.
        "next_action": render_next_action("exported" if export_record["google_url"] else "exported_file"),
    })
    return base


# -- CLI ---------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a stored Morning Report to Google Docs/Slides/PDF")
    parser.add_argument("--list", action="store_true", help="List recent reports instead of exporting.")
    parser.add_argument("--limit", type=int, default=10, help="How many runs to list.")
    parser.add_argument("--run-dir", dest="run_dir", help="Export this exact run directory.")
    parser.add_argument("--topic", help="Pick the newest report whose topic (or title) matches.")
    parser.add_argument("--date", help="Restrict to one day (YYYY-MM-DD).")
    parser.add_argument("--latest", action="store_true", help="Newest report (the default).")
    parser.add_argument("--to", dest="target", default=DEFAULT_TARGET, choices=TARGETS)
    parser.add_argument("--title", default="", help="Override the document title.")
    parser.add_argument("--again", action="store_true",
                        help="Make a new file even if this report was exported before.")
    parser.add_argument("--image-query", dest="image_query", action="append", default=[],
                        help="One SHORT ENGLISH image query per section, in section order "
                             "(repeatable). Pass \"\" to leave a section without a picture.")
    parser.add_argument("--no-auto-images", dest="no_auto_images", action="store_true",
                        help="Never illustrate this export.")
    parser.add_argument("--history-dir", dest="history_dir", default=str(HISTORY_DIR))
    parser.add_argument("--convert-script", dest="convert_script", default=None)
    return parser


def _emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    history_dir = Path(args.history_dir)
    convert_script = Path(args.convert_script) if args.convert_script else None

    if args.list:
        runs = list_runs(history_dir)[: max(1, args.limit)]
        return _emit({
            "success": True,
            "reports": runs,
            "next_action": render_next_action("listed" if runs else "no_runs"),
        })

    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.exists():
            return _emit({
                "success": False,
                "error": "run_dir_not_found",
                "run_dir": str(run_dir),
                "next_action": render_next_action("failed", error="that report directory no longer exists"),
            })
        run = describe_run(run_dir)
    else:
        runs = list_runs(history_dir)
        if not runs:
            return _emit({
                "success": False,
                "error": "no_runs",
                "reports": [],
                "next_action": render_next_action("no_runs"),
            })
        run, _candidates = resolve_run(runs, topic=args.topic or "", date=args.date or "")
        if run is None:
            return _emit({
                "success": False,
                "error": "no_match",
                "requested": {"topic": args.topic or "", "date": args.date or ""},
                "available": runs[:10],
                "next_action": render_next_action("no_match"),
            })

    return _emit(export_run(
        run,
        target=args.target,
        title=args.title,
        again=args.again,
        convert_script=convert_script,
        image_queries=args.image_query,
        no_auto_images=args.no_auto_images,
    ))


if __name__ == "__main__":
    sys.exit(main())
