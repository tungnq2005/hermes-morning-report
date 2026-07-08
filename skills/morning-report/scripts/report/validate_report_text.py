#!/usr/bin/env python3
"""Validate Morning Report text before delivery."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
TITLE_RE = re.compile(r"^\s*#\s+\S+", re.MULTILINE)
SECTION_RE = re.compile(r"^\s*##\s+\S+", re.MULTILINE)
SUBSECTION_RE = re.compile(r"^\s*###\s+\S+", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)", re.IGNORECASE)
MARKDOWN_LINK_URL_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)", re.IGNORECASE)
TITLE_LINE_RE = re.compile(r"^\s*#\s+(.+)$", re.MULTILINE)
DECORATIVE_SYMBOL_RE = re.compile(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]")
BAD_RE = re.compile(
    r"\b(?:Topic Plan|Source Plan|search progress|fetch progress|debug|traceback|MEDIA:|audio generated successfully|recording history)\b",
    re.IGNORECASE,
)

STYLE_RULES = {
    "concise": {"min_sections": 3, "min_bullets": 5, "max_words": 700},
    "deep_analysis": {"min_sections": 4, "min_bullets": 6, "max_words": 900},
    "opportunities_risks": {"min_sections": 5, "min_bullets": 8, "max_words": 900},
}


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def markdown_link_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw in MARKDOWN_LINK_URL_RE.findall(text):
        url = raw.strip()
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def allowed_source_urls(source_manifest: dict[str, Any] | None) -> set[str]:
    if not source_manifest:
        return set()
    entries = source_manifest.get("fetched_sources")
    if not isinstance(entries, list) or not entries:
        entries = source_manifest.get("sources", [])
    allowed: set[str] = set()
    if not isinstance(entries, list):
        return allowed
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fetch = entry.get("fetch") if isinstance(entry.get("fetch"), dict) else {}
        for raw in (entry.get("url"), entry.get("canonical_url"), fetch.get("final_url")):
            if isinstance(raw, str) and raw.strip():
                allowed.add(normalize_url(raw))
    return allowed


def validate_report(text: str, style: str, source_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    clean = text.strip()
    rules = STYLE_RULES.get(style)
    issues: list[dict[str, str]] = []

    if rules is None:
        issues.append({"code": "unknown_style", "message": f"Unsupported style: {style}"})
        rules = STYLE_RULES["concise"]

    words = count_words(clean)
    sections = len(SECTION_RE.findall(clean))
    subsections = len(SUBSECTION_RE.findall(clean))
    bullets = len(BULLET_RE.findall(clean))
    link_urls = markdown_link_urls(clean)
    links = len(link_urls)

    if not clean:
        issues.append({"code": "empty_report", "message": "Report is empty."})
    if not clean.startswith("# "):
        issues.append({"code": "missing_title", "message": "Report must start with a Markdown title."})
    if not TITLE_RE.search(clean):
        issues.append({"code": "invalid_title", "message": "Report title is missing or malformed."})
    title_match = TITLE_LINE_RE.search(clean)
    if title_match and DECORATIVE_SYMBOL_RE.search(title_match.group(1)):
        issues.append({"code": "decorative_symbol_in_title", "message": "Remove decorative emoji/symbols from the report title."})
    if sections < rules["min_sections"]:
        issues.append(
            {
                "code": "too_few_sections",
                "message": f"Report has {sections} sections; minimum is {rules['min_sections']}.",
            }
        )
    if bullets < rules["min_bullets"]:
        issues.append(
            {
                "code": "too_few_bullets",
                "message": f"Report has {bullets} bullets; minimum is {rules['min_bullets']}.",
            }
        )
    if words > rules["max_words"]:
        issues.append(
            {
                "code": "too_long",
                "message": f"Report has {words} words; maximum is {rules['max_words']}.",
            }
        )

    bad = BAD_RE.search(clean)
    if bad:
        issues.append({"code": "internal_text_present", "message": "Remove internal workflow text.", "sample": bad.group(0)})
    if links == 0:
        issues.append({"code": "missing_evidence_links", "message": "Report needs at least one Markdown evidence link."})
    allowed_urls = allowed_source_urls(source_manifest)
    if allowed_urls:
        unfetched = [url for url in link_urls if normalize_url(url) not in allowed_urls]
        if unfetched:
            issues.append(
                {
                    "code": "unfetched_evidence_link",
                    "message": "Evidence links must use only fetched source URLs.",
                    "sample": unfetched[0],
                }
            )
    if style in {"deep_analysis", "opportunities_risks"} and subsections == 0:
        issues.append({"code": "missing_subsections", "message": "This style needs subsection headings."})

    return {
        "success": not issues,
        "ok": not issues,
        "style": style,
        "word_count": words,
        "section_count": sections,
        "subsection_count": subsections,
        "bullet_count": bullets,
        "evidence_link_count": links,
        "allowed_evidence_link_count": len(allowed_urls),
        "issues": issues,
    }


def validate_report_phase(args: argparse.Namespace) -> dict[str, Any]:
    from report.common import load_run_state, read_json, runner_command, save_run_state

    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    report_file = Path(args.report_file or state["report_file"])
    report_text = report_file.read_text(encoding="utf-8")
    source_manifest_path = state.get("source_collection", {}).get("manifest_path")
    source_manifest = read_json(Path(source_manifest_path)) if source_manifest_path else None
    validation = validate_report(report_text, state["config"]["report_style"], source_manifest)
    state["validation"] = {"report": validation}
    state["report_file"] = str(report_file)

    if validation["ok"]:
        state["report_output"] = {
            "status": "ready_to_send",
            "report_file": str(report_file),
            "text_char_count": len(report_text),
        }
        state["next_action"] = {
            "type": "send_report",
            "report_file": str(report_file),
            "message_goal": "Send the text report exactly as written through Telegram.",
            "next_command": runner_command("record-report", work_dir),
        }
    else:
        state["next_action"] = {
            "type": "revise_report",
            "message_goal": "Revise the report once using validation.issues, then run validate-report again.",
            "next_command": runner_command("validate-report", work_dir),
        }

    save_run_state(work_dir, state)
    return {
        "success": validation["ok"],
        "phase": "validate-report",
        "can_continue": validation["ok"],
        "work_dir": str(work_dir),
        "report_file": str(report_file),
        "config": state["config"],
        "validation": {"report": validation},
        "report_output": state.get("report_output", {}),
        "audio": state.get("audio", {}),
        "next_action": state["next_action"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Morning Report text")
    parser.add_argument("--report-file", required=True, help="Report Markdown file, or '-' for stdin")
    parser.add_argument("--style", required=True, choices=sorted(STYLE_RULES))
    parser.add_argument("--no-fail", action="store_true")
    return parser


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate_report(read_input(args.report_file), args.style)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] or args.no_fail else 1
    except Exception as exc:
        print(f"report/validate_report_text.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
