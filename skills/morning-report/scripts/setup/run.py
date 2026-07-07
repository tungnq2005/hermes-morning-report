#!/usr/bin/env python3
"""Run Morning Report setup readiness phases."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

LOG_TEMPLATES = Path(__file__).resolve().parent / "action_templates.json"

from setup.common import (  # noqa: E402
    DEFAULT_AGENTS,
    DEFAULT_STATE,
    DEFAULT_USER,
)
from setup.system_readiness import run_system_phase  # noqa: E402
from setup.tool_readiness import run_tools_phase  # noqa: E402


class TemplateContext(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_log_templates(path: Path = LOG_TEMPLATES) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"setup log templates must be a JSON object: {path}")
    return data


def render_value(value: Any, context: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format_map(TemplateContext(context))
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return value


def render_log_template(name: str, context: dict[str, str]) -> dict[str, Any]:
    template = load_log_templates()[name]
    if not isinstance(template, dict):
        raise ValueError(f"setup log template must be an object: {name}")
    return render_value(template, context)


def print_log_template(name: str, context: dict[str, str]) -> None:
    try:
        output = render_log_template(name, context)
    except Exception as exc:
        output = {
            "status": f"Setup log template could not be rendered: {exc}.",
            "next_action": {
                "instructions": [
                    "Fix the setup log template JSON, then rerun setup.",
                ]
            },
        }
    print(json.dumps(output, ensure_ascii=False))


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print_log_template("invalid_arguments", {"error": message})
        raise SystemExit(2)


def config_status_command(*, state: Path, user: Path) -> str:
    return " ".join(
        [
            "python3",
            "skills/morning-report/scripts/config_status.py",
            "--state",
            shlex.quote(str(state)),
            "--user",
            shlex.quote(str(user)),
            "--compact",
        ]
    )


def status_and_next_action_from_template(name: str, context: dict[str, str]) -> tuple[str, dict[str, Any]]:
    output = render_log_template(name, context)
    return str(output["status"]), output["next_action"]


def phase_command(args: argparse.Namespace, phase: str) -> str:
    parts = [
        "python3",
        "skills/morning-report/scripts/setup/run.py",
        phase,
        "--agent",
        "--compact",
    ]
    if args.full_readiness:
        parts.append("--full-readiness")
    if args.check_cron_status:
        parts.append("--check-cron-status")
    if args.check_tts:
        parts.append("--check-tts")
    if args.tts_lang:
        parts.extend(["--tts-lang", args.tts_lang])
    if args.check_model:
        parts.append("--check-model")
    if args.probe_model:
        parts.append("--probe-model")
    if args.check_web_tools:
        parts.append("--check-web-tools")
    if args.check_channel_status:
        parts.append("--check-channel-status")
    if args.check_fallbacks:
        parts.append("--check-fallbacks")
    if args.no_cli:
        parts.append("--no-cli")
    if args.state != str(DEFAULT_STATE):
        parts.extend(["--state", args.state])
    if args.user != str(DEFAULT_USER):
        parts.extend(["--user", args.user])
    if args.agents != str(DEFAULT_AGENTS):
        parts.extend(["--agents", args.agents])
    if phase == "tools" or args.agents_reviewed:
        parts.append("--agents-reviewed")
    return " ".join(shlex.quote(str(part)) for part in parts)


def render_readiness_result(
    *,
    problems: list[str],
    warnings: list[str],
    fallback_template: str,
    context: dict[str, str],
) -> tuple[str, dict[str, Any]]:
    if problems:
        if len(problems) == 1:
            try:
                return status_and_next_action_from_template(problems[0], context)
            except KeyError:
                pass
        return status_and_next_action_from_template("required_readiness_failed", context)

    if warnings:
        if len(warnings) == 1:
            try:
                return status_and_next_action_from_template(warnings[0], context)
            except KeyError:
                pass
        return status_and_next_action_from_template(f"{fallback_template}_with_notes", context)

    return status_and_next_action_from_template(fallback_template, context)


def build_system_result(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    agents = Path(args.agents)
    check_cron_status_enabled = args.check_cron_status or args.full_readiness
    system_phase = run_system_phase(
        agents=agents,
        timeout=args.timeout,
        no_cli=args.no_cli,
        check_cron_status_enabled=check_cron_status_enabled,
        agents_reviewed=args.agents_reviewed,
    )
    context = {
        "problems": ", ".join(system_phase.problems),
        "warnings": ", ".join(system_phase.warnings),
        "tool_command": phase_command(args, "tools"),
    }

    if system_phase.problems:
        status, next_action = render_readiness_result(
            problems=system_phase.problems,
            warnings=[],
            fallback_template="system_ready",
            context=context,
        )
        return {"status": status, "next_action": next_action}, False

    if not system_phase.workspace_router_exists:
        status, next_action = status_and_next_action_from_template("workspace_rules_missing", context)
        return {"status": status, "next_action": next_action}, False

    if not args.agents_reviewed:
        context["rerun_command"] = phase_command(args, "system") + " --agents-reviewed"
        status, next_action = status_and_next_action_from_template("workspace_review_required", context)
        return {"status": status, "next_action": next_action}, False

    if system_phase.warnings:
        status, next_action = status_and_next_action_from_template("system_ready_with_notes", context)
    else:
        status, next_action = status_and_next_action_from_template("system_ready", context)
    return {"status": status, "next_action": next_action}, True


def build_tools_result(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    state = Path(args.state)
    user = Path(args.user)
    check_model_enabled = args.check_model or args.full_readiness
    probe_model_enabled = args.probe_model or args.full_readiness
    check_web_tools_enabled = args.check_web_tools or args.full_readiness
    check_channel_status_enabled = args.check_channel_status or args.full_readiness
    check_fallbacks_enabled = args.check_fallbacks or args.full_readiness

    tools_phase = run_tools_phase(
        timeout=args.timeout,
        no_cli=args.no_cli,
        check_model_enabled=check_model_enabled,
        probe_model_enabled=probe_model_enabled,
        check_web_tools_enabled=check_web_tools_enabled,
        check_channel_status_enabled=check_channel_status_enabled,
        check_fallbacks_enabled=check_fallbacks_enabled,
        check_tts_enabled=args.check_tts,
        tts_language=args.tts_lang,
    )
    context = {
        "problems": ", ".join(tools_phase.problems),
        "warnings": ", ".join(tools_phase.warnings),
        "config_command": config_status_command(state=state, user=user),
    }
    status, next_action = render_readiness_result(
        problems=tools_phase.problems,
        warnings=tools_phase.warnings,
        fallback_template="ready",
        context=context,
    )
    return {"status": status, "next_action": next_action}, not tools_phase.problems


def build_setup_phase(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if args.phase == "system":
        return build_system_result(args)
    return build_tools_result(args)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Run Morning Report setup readiness checks")
    parser.add_argument("phase", choices=["system", "tools"])
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--user", default=str(DEFAULT_USER))
    parser.add_argument("--agents", default=str(DEFAULT_AGENTS))
    parser.add_argument("--agents-reviewed", action="store_true")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--check", action="store_true", help="Exit 0 only when setup checks are ready for config status")
    parser.add_argument("--env-check", action="store_true", help="Exit 0 only when environment checks pass")
    parser.add_argument("--check-cron-status", action="store_true", help="Probe cron status through the gateway")
    parser.add_argument("--check-tts", action="store_true", help="Probe Google TTS network access for an explicit language")
    parser.add_argument("--tts-lang", help="Report language/language code to use for TTS probing")
    parser.add_argument("--check-model", action="store_true", help="Check model provider auth through OpenClaw")
    parser.add_argument("--probe-model", action="store_true", help="Use live model provider probing when checking model auth")
    parser.add_argument("--check-web-tools", action="store_true", help="Probe web search through OpenClaw infer; fetch is verified during report runs")
    parser.add_argument("--check-channel-status", action="store_true", help="Probe OpenClaw channel status")
    parser.add_argument("--check-fallbacks", action="store_true", help="Inspect model fallback configuration")
    parser.add_argument("--full-readiness", action="store_true", help="Run setup-time readiness checks that do not require customer preferences")
    parser.add_argument("--no-cli", action="store_true", help="Skip OpenClaw CLI checks")
    parser.add_argument("--agent", action="store_true", help="Omit raw check details for prompt-facing setup flow")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    return parser


def agent_result(result: dict[str, Any]) -> dict[str, Any]:
    return result


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result, phase_ok = build_setup_phase(args)
    if args.agent:
        result = agent_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    if args.check and not phase_ok:
        return 1
    if args.env_check and not phase_ok:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print_log_template("setup_runner_exception", {"error": str(exc)})
        raise SystemExit(1)
