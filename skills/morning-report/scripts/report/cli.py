"""CLI for Morning Report run phases."""

from __future__ import annotations

import argparse
from typing import Callable, Any

from report.common import (
    DEFAULT_AUDIO_FILE,
    DEFAULT_AUDIO_SCRIPT_FILE,
    DEFAULT_REPORT_FILE,
    DEFAULT_TARGET_FETCHED,
    DEFAULT_USER,
    DEFAULT_STATE,
    DEFAULT_WORK_DIR,
    print_result,
)
from report.audit_events import DEFAULT_AUDIT_LOG
from report.generate_audio_file import generate_audio_phase
from report.record_audio_history import record_audio_phase
from report.record_report_history import DEFAULT_HISTORY_DIR, record_report_phase
from report.source_collection import fetch_phase, search_phase
from report.web_source_collector import DEFAULT_SEARCH_FALLBACK_PROVIDER, DEFAULT_SEARCH_PROVIDER
from report.validate_audio_script import (
    DEFAULT_MAX_WORDS as AUDIO_MAX_WORDS,
    DEFAULT_MIN_WORDS as AUDIO_MIN_WORDS,
    DEFAULT_WORDS_PER_MINUTE as AUDIO_WPM,
    validate_audio_phase,
)
from report.validate_report_text import validate_report_phase


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--agent", action="store_true", help="Print prompt-facing JSON")
    parser.add_argument("--compact", action="store_true")


def add_search_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--user", default=str(DEFAULT_USER))
    parser.add_argument("--report-file", default=str(DEFAULT_REPORT_FILE))
    parser.add_argument("--audio-script-file", default=str(DEFAULT_AUDIO_SCRIPT_FILE))
    parser.add_argument("--audio-file", default=str(DEFAULT_AUDIO_FILE))
    parser.add_argument("--query", action="append")
    parser.add_argument("--provider", default=DEFAULT_SEARCH_PROVIDER)
    parser.add_argument("--fallback-provider", default=DEFAULT_SEARCH_FALLBACK_PROVIDER)
    parser.add_argument("--max-search-calls", type=int, default=5)
    parser.add_argument("--limit-per-call", type=int, default=10)
    parser.add_argument("--include-social", action="store_true")
    parser.add_argument("--search-timeout", type=int, default=30)


def add_fetch_args(parser: argparse.ArgumentParser, *, include_social: bool = True) -> None:
    parser.add_argument("--target-fetched", type=int, default=DEFAULT_TARGET_FETCHED)
    parser.add_argument("--freshness-hours", type=int, default=24)
    if include_social:
        parser.add_argument("--include-social", action="store_true")
    parser.add_argument("--fetch-timeout", type=int, default=20)
    parser.add_argument("--max-fetch-bytes", type=int, default=500_000)
    parser.add_argument("--min-text-chars", type=int, default=400)


def add_audio_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audio-script-file")
    parser.add_argument("--audio-file")
    parser.add_argument("--speed", type=float, default=1.2)
    parser.add_argument("--chunk-limit", type=int, default=180)
    parser.add_argument("--min-words", type=int, default=AUDIO_MIN_WORDS)
    parser.add_argument("--max-words", type=int, default=AUDIO_MAX_WORDS)
    parser.add_argument("--wpm", type=int, default=AUDIO_WPM)


def add_record_report_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--report-file")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--user", default=str(DEFAULT_USER))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG))
    parser.add_argument("--send-status", default="sent")
    parser.add_argument("--audio-status")


def add_record_audio_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audio-script-file")
    parser.add_argument("--audio-file")
    parser.add_argument("--audio-manifest")
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--audit-log", default=str(DEFAULT_AUDIT_LOG))
    parser.add_argument("--send-status", default="sent")
    parser.add_argument("--audio-status")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Morning Report phases through one entrypoint")
    sub = parser.add_subparsers(dest="command", required=True)

    search_parser = sub.add_parser("search", help="Check config and prepare source search plan")
    add_common_args(search_parser)
    add_search_args(search_parser)

    fetch_parser = sub.add_parser("fetch", help="Search, dedupe, validate 24h freshness, and fetch sources")
    add_common_args(fetch_parser)
    add_fetch_args(fetch_parser)

    validate_report_parser = sub.add_parser("validate-report", help="Validate report and prepare Telegram text send action")
    add_common_args(validate_report_parser)
    validate_report_parser.add_argument("--report-file")

    validate_audio_parser = sub.add_parser("validate-audio", help="Validate the saved audio script")
    add_common_args(validate_audio_parser)
    validate_audio_parser.add_argument("--audio-script-file")
    validate_audio_parser.add_argument("--min-words", type=int, default=AUDIO_MIN_WORDS)
    validate_audio_parser.add_argument("--max-words", type=int, default=AUDIO_MAX_WORDS)
    validate_audio_parser.add_argument("--wpm", type=int, default=AUDIO_WPM)

    generate_audio_parser = sub.add_parser("generate-audio", help="Generate MP3 from the validated audio script")
    add_common_args(generate_audio_parser)
    add_audio_args(generate_audio_parser)

    record_report_parser = sub.add_parser("record-report", help="Record text report history after Telegram send")
    add_common_args(record_report_parser)
    add_record_report_args(record_report_parser)

    record_audio_parser = sub.add_parser("record-audio", help="Record audio history after Telegram send")
    add_common_args(record_audio_parser)
    add_record_audio_args(record_audio_parser)

    return parser


def phase_map() -> dict[str, Callable[[Any], dict[str, Any]]]:
    return {
        "search": search_phase,
        "fetch": fetch_phase,
        "validate-report": validate_report_phase,
        "validate-audio": validate_audio_phase,
        "generate-audio": generate_audio_phase,
        "record-report": record_report_phase,
        "record-audio": record_audio_phase,
    }


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = phase_map()[args.command](args)
        print_result(result, agent=args.agent, compact=args.compact)
        non_hard_fail_commands = {
            "validate-report",
            "validate-audio",
            "generate-audio",
            "record-report",
            "record-audio",
        }
        return 0 if result.get("success") or args.command in non_hard_fail_commands else 1
    except Exception as exc:
        error = {
            "success": False,
            "phase": getattr(args, "command", "unknown"),
            "can_continue": False,
            "error": str(exc),
            "next_action": {
                "type": "stop",
                "message_goal": "Tell the user the run helper failed before report send.",
            },
        }
        print_result(error, agent=getattr(args, "agent", False), compact=getattr(args, "compact", False))
        return 1
