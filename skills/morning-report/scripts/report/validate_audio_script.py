#!/usr/bin/env python3
"""Validate a Morning Report audio script before TTS generation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MIN_WORDS = 540
DEFAULT_MAX_WORDS = 900
DEFAULT_WORDS_PER_MINUTE = 180

WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((?:https?://|mailto:)[^)]+\)", re.IGNORECASE)
MEDIA_RE = re.compile(r"\bMEDIA:", re.IGNORECASE)
SOURCE_LABEL_RE = re.compile(r"\b(?:Source|Sources|Evidence):", re.IGNORECASE)
CODE_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
FILE_PATH_RE = re.compile(r"(?:^|\s)(?:/tmp/|skills/morning-report/|state/audio-history/|state/report-history/)\S*")
DEBUG_RE = re.compile(
    r"\b(?:traceback|stack trace|api key|token|provider log|manifest\.json|chunk-\d+|ffmpeg|curl exited)\b",
    re.IGNORECASE,
)
HYPE_RE = re.compile(
    r"\b(?:shockingly|surged|soared|slashed|clear runway|exploded|crashed|skyrocketed)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def validate_script(text: str, min_words: int, max_words: int, wpm: int) -> dict[str, Any]:
    normalized = normalize_text(text)
    word_count = count_words(normalized)
    issues: list[dict[str, str]] = []

    if not normalized:
        issues.append({"code": "empty_script", "message": "Audio script is empty."})
    if min_words > 0 and word_count < min_words:
        issues.append(
            {
                "code": "under_min_words",
                "message": f"Audio script has {word_count} words; minimum is {min_words}.",
            }
        )
    if max_words > 0 and word_count > max_words:
        issues.append(
            {
                "code": "over_max_words",
                "message": f"Audio script has {word_count} words; maximum is {max_words}.",
            }
        )

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
        "success": not issues,
        "ok": not issues,
        "word_count": word_count,
        "char_count": len(normalized),
        "target_min_words": min_words,
        "target_max_words": max_words,
        "words_per_minute": wpm,
        "estimated_minutes": estimated_minutes,
        "issues": issues,
    }


def validate_audio_phase(args: argparse.Namespace) -> dict[str, Any]:
    from report.common import load_run_state, runner_command, save_run_state

    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    audio_file = Path(args.audio_script_file or state["audio_script_file"])
    attempts = int(state.get("audio", {}).get("validation_attempts", 0)) + 1
    validation = validate_script(audio_file.read_text(encoding="utf-8"), args.min_words, args.max_words, args.wpm)
    audio = state.setdefault("audio", {})
    audio["validation_attempts"] = attempts
    audio["script_file"] = str(audio_file)
    audio["validation"] = validation

    if validation["ok"]:
        audio["status"] = "validated"
        next_action = {
            "type": "generate_audio",
            "command": runner_command("generate-audio", work_dir),
            "message_goal": "Generate MP3 from the validated audio script.",
        }
    elif attempts >= 2:
        audio["status"] = "failed"
        audio["failure_reason"] = "audio_script_validation_failed"
        next_action = {
            "type": "audio_failed_notice",
            "message_goal": "Tell the user the text report was sent but audio could not be generated cleanly.",
            "next_command": runner_command("record-audio", work_dir, "--audio-status", "failed", "--send-status", "failure_notice_sent"),
        }
    else:
        audio["status"] = "needs_revision"
        next_action = {
            "type": "revise_audio_script",
            "message_goal": "Revise the audio script once using validation.issues, then run validate-audio again.",
            "next_command": runner_command("validate-audio", work_dir),
        }

    state["next_action"] = next_action
    save_run_state(work_dir, state)
    return {
        "success": validation["ok"],
        "phase": "validate-audio",
        "can_continue": validation["ok"],
        "work_dir": str(work_dir),
        "audio_script_file": str(audio_file),
        "config": state["config"],
        "validation": {"audio_script": validation},
        "audio": audio,
        "next_action": next_action,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Morning Report audio script")
    parser.add_argument("--text-file", required=True, help="Audio script text file, or '-' for stdin")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument("--wpm", type=int, default=DEFAULT_WORDS_PER_MINUTE)
    parser.add_argument("--no-fail", action="store_true", help="Always exit 0 while still reporting issues")
    return parser


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = validate_script(read_input(args.text_file), args.min_words, args.max_words, args.wpm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] or args.no_fail else 1
    except Exception as exc:
        print(f"report/validate_audio_script.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
