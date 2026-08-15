#!/usr/bin/env python3
"""Validate Morning Report text (report or audio script)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from helpers.history import record_report_validation

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
OUTPUT_TEMPLATES_PATH = SKILL_DIR / "references" / "workflow-output-templates.json"

# ── Shared ─────────────────────────────────────────────────────────────
WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)

# ── Report ─────────────────────────────────────────────────────────────
TITLE_RE = re.compile(r"^\s*#\s+\S+", re.MULTILINE)
SECTION_RE = re.compile(r"^\s*##\s+\S+", re.MULTILINE)
SUBSECTION_RE = re.compile(r"^\s*###\s+\S+", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)", re.IGNORECASE)
TITLE_LINE_RE = re.compile(r"^\s*#\s+(.+)$", re.MULTILINE)
DECORATIVE_SYMBOL_RE = re.compile(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]")
BAD_RE = re.compile(
    r"\b(?:Topic Plan|Source Plan|search progress|fetch progress|debug|traceback|MEDIA:|audio generated successfully|recording history)\b",
    re.IGNORECASE,
)

STYLE_RULES = {
    "concise": {"min_sections": 3, "min_bullets": 5, "min_words": 400, "max_words": 600},
    "deep_analysis": {"min_sections": 4, "min_bullets": 6, "min_words": 900, "max_words": 1200},
    "opportunities_risks": {"min_sections": 5, "min_bullets": 8, "min_words": 900, "max_words": 1200},
}

# ── Audio ──────────────────────────────────────────────────────────────
DEFAULT_MIN_WORDS = 680
DEFAULT_MAX_WORDS = 930
DEFAULT_WPM = 189

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MEDIA_RE = re.compile(r"\bMEDIA:", re.IGNORECASE)
SOURCE_LABEL_RE = re.compile(r"\b(?:Source|Sources|Evidence):", re.IGNORECASE)
CODE_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
FILE_PATH_RE = re.compile(r"(?:^|\s)(?:/tmp/|skills/morning-report/|state/history/)\S*")
DEBUG_RE = re.compile(
    r"\b(?:traceback|stack trace|api[ _-]key|access[ _-]token|api[ _-]?token|provider log|manifest\.json|chunk-\d+|ffmpeg|curl exited)\b",
    re.IGNORECASE,
)
HYPE_RE = re.compile(
    r"\b(?:shockingly|surged|soared|slashed|clear runway|exploded|crashed|skyrocketed)\b",
    re.IGNORECASE,
)


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


# ── Report validation ─────────────────────────────────────────────────
def validate_report(text: str, style: str) -> dict[str, Any]:
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
    links = len(MARKDOWN_LINK_RE.findall(clean))

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
        issues.append({"code": "too_few_sections", "message": f"Report has {sections} sections; minimum is {rules['min_sections']}."})
    if bullets < rules["min_bullets"]:
        issues.append({"code": "too_few_bullets", "message": f"Report has {bullets} bullets; minimum is {rules['min_bullets']}."})
    if words > rules["max_words"]:
        issues.append({"code": "too_long", "message": f"Report has {words} words; maximum is {rules['max_words']}."})
    if rules.get("min_words") and words < rules["min_words"]:
        issues.append({"code": "too_short", "message": f"Report has {words} words; minimum is {rules['min_words']}."})

    bad = BAD_RE.search(clean)
    if bad:
        issues.append({"code": "internal_text_present", "message": "Remove internal workflow text.", "sample": bad.group(0)})
    if links == 0:
        issues.append({"code": "missing_evidence_links", "message": "Report needs at least one Markdown evidence link."})
    if style in {"deep_analysis", "opportunities_risks"} and subsections == 0:
        issues.append({"code": "missing_subsections", "message": "This style needs subsection headings."})

    return {
        "ok": not issues,
        "issues": issues,
    }


# ── Audio validation ──────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def validate_audio(text: str, min_words: int, max_words: int, wpm: int) -> dict[str, Any]:
    normalized = normalize_text(text)
    word_count = count_words(normalized)
    issues: list[dict[str, str]] = []

    if not normalized:
        issues.append({"code": "empty_script", "message": "Audio script is empty."})
    if min_words > 0 and word_count < min_words:
        issues.append({"code": "under_min_words", "message": f"Audio script has {word_count} words; minimum is {min_words}."})
    if max_words > 0 and word_count > max_words:
        issues.append({"code": "over_max_words", "message": f"Audio script has {word_count} words; maximum is {max_words}."})

    pattern_checks = [
        ("url_present", URL_RE, "Remove URLs from the spoken audio script."),
        ("markdown_link_present", MARKDOWN_LINK_RE, "Remove Markdown links from the spoken audio script."),
        ("media_directive_present", MEDIA_RE, "Do not include MEDIA directives in the audio script."),
        ("source_label_present", SOURCE_LABEL_RE, "Avoid repeated Source/Evidence labels in spoken audio."),
        ("code_fence_present", CODE_FENCE_RE, "Do not include code fences in the audio script."),
        ("table_present", TABLE_ROW_RE, "Do not include tables in the audio script."),
        ("file_path_present", FILE_PATH_RE, "Do not include local file paths in the audio script."),
        ("debug_text_present", DEBUG_RE, "Do not include debug/runtime text in the audio script."),
        ("hype_language_present", HYPE_RE, "Use calm, non-sensational wording in the audio script."),
    ]
    for code, pattern, message in pattern_checks:
        sample = first_match(pattern, normalized)
        if sample:
            issues.append({"code": code, "message": message, "sample": sample[:120]})

    estimated_minutes = round(word_count / wpm, 2) if wpm > 0 else None
    return {
        "ok": not issues,
        "type": "audio",
        "word_count": word_count,
        "char_count": len(normalized),
        "estimated_minutes": estimated_minutes,
        "issues": issues,
    }


# ── CLI ────────────────────────────────────────────────────────────────
def load_validate_report_templates() -> dict[str, Any]:
    data = json.loads(OUTPUT_TEMPLATES_PATH.read_text(encoding="utf-8"))
    steps = data.get("steps", {})
    templates = steps.get("validate_report", {}) if isinstance(steps, dict) else {}
    if not isinstance(templates, dict):
        raise RuntimeError("Invalid validate_report output templates")
    return templates


def render_validate_report_output(result: dict[str, Any]) -> dict[str, Any]:
    template_name = "valid" if result["ok"] else "invalid"
    template = load_validate_report_templates().get(template_name)
    if not isinstance(template, dict):
        raise RuntimeError(f"Missing validate_report output template: {template_name}")
    output = dict(template)
    if result["issues"]:
        output["issues"] = result["issues"]
    return output


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate Morning Report text")
    p.add_argument("--type", required=True, choices=["report", "audio"], help="Validation type")
    # Report args
    p.add_argument("--report-file", help="Report Markdown file, or '-' for stdin")
    p.add_argument("--style", choices=sorted(STYLE_RULES))
    # Audio args
    p.add_argument("--text-file", help="Audio script text file, or '-' for stdin")
    p.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    p.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    p.add_argument("--wpm", type=int, default=DEFAULT_WPM)
    # Shared
    p.add_argument("--run-dir", help="History run directory")
    p.add_argument("--no-fail", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.type == "report":
            text = read_input(args.report_file)
            result = validate_report(text, args.style)
            if args.run_dir:
                if args.report_file == "-":
                    raise ValueError("--run-dir requires --report-file to be a file path")
                record_report_validation(Path(args.run_dir), Path(args.report_file), result["ok"])
            print(json.dumps(render_validate_report_output(result), ensure_ascii=False, separators=(",", ":")))
            return 0
        else:
            result = validate_audio(read_input(args.text_file), args.min_words, args.max_words, args.wpm)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] or args.no_fail else 1
    except Exception as exc:
        print(f"validate.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
