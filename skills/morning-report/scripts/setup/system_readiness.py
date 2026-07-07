"""System readiness phase for Morning Report setup."""

from __future__ import annotations

from dataclasses import dataclass
import shutil
from pathlib import Path
from typing import Any

from setup.common import command_result


@dataclass
class SystemReadiness:
    problems: list[str]
    warnings: list[str]
    workspace_router_exists: bool
    workspace_router_ready: bool


def check_openclaw(timeout: int) -> dict[str, Any]:
    path = shutil.which("openclaw")
    result: dict[str, Any] = {"ok": bool(path), "path": path}
    if not path:
        result["error"] = "openclaw CLI not found on PATH"
        return result
    help_check = command_result(["openclaw", "--help"], timeout)
    result["help_check"] = help_check
    result["ok"] = bool(help_check.get("ok"))
    return result


def check_cron_help(timeout: int) -> dict[str, Any]:
    if not shutil.which("openclaw"):
        return {
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    return command_result(["openclaw", "cron", "--help"], timeout)


def check_cron_status(timeout: int) -> dict[str, Any]:
    if not shutil.which("openclaw"):
        return {
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    result = command_result(["openclaw", "cron", "status"], timeout)
    combined = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
    if "GatewaySecretRefUnavailableError" in combined:
        result["secret_ref_unavailable"] = True
    return result


def check_workspace_router(agents: Path) -> dict[str, Any]:
    return {
        "ok": agents.exists(),
        "path": str(agents),
        "exists": agents.exists(),
    }


def run_system_phase(
    *,
    agents: Path,
    timeout: int,
    no_cli: bool,
    check_cron_status_enabled: bool,
    agents_reviewed: bool,
) -> SystemReadiness:
    workspace_router = check_workspace_router(agents)
    workspace_router["reviewed"] = bool(agents_reviewed)
    workspace_router["ready"] = bool(workspace_router["exists"] and agents_reviewed)
    checks: dict[str, Any] = {"workspace_router": workspace_router}

    if no_cli:
        checks["openclaw_cli"] = {"ok": None, "skipped": True}
        checks["cron_help"] = {"ok": None, "skipped": True}
        if check_cron_status_enabled:
            checks["cron_status"] = {"checked": False, "skipped": True}
    else:
        checks["openclaw_cli"] = check_openclaw(timeout)
        checks["cron_help"] = check_cron_help(timeout)
        if check_cron_status_enabled:
            checks["cron_status"] = check_cron_status(timeout)

    problems: list[str] = []
    warnings: list[str] = []

    if not no_cli:
        if not checks["openclaw_cli"].get("ok"):
            problems.append("openclaw_cli_unavailable")
        if not checks["cron_help"].get("ok"):
            problems.append("cron_cli_unavailable")
        cron_status = checks.get("cron_status")
        if check_cron_status_enabled and isinstance(cron_status, dict):
            if cron_status.get("secret_ref_unavailable"):
                warnings.append("gateway_secret_ref_unavailable")
            if not cron_status.get("ok"):
                problems.append("cron_status_unverified")

    return SystemReadiness(
        problems=problems,
        warnings=warnings,
        workspace_router_exists=bool(workspace_router["exists"]),
        workspace_router_ready=bool(workspace_router["ready"]),
    )
