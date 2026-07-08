"""Tool readiness phase for Morning Report setup."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from typing import Any

from setup.common import command_json_result
from tts_languages import check_google_tts_language, resolve_tts_language

PRIMARY_SEARCH_PROVIDER = "brave"
FALLBACK_SEARCH_PROVIDER = "exa"


@dataclass
class ToolReadiness:
    problems: list[str]
    warnings: list[str]


def check_model_runtime(check_model: bool, probe_model: bool, timeout: int) -> dict[str, Any]:
    if not check_model:
        return {"checked": False}
    if not shutil.which("openclaw"):
        return {
            "checked": True,
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    cmd = ["openclaw", "models", "status", "--json", "--check"]
    if probe_model:
        cmd.extend(["--probe", "--probe-timeout", str(timeout * 1000), "--probe-max-tokens", "8"])
    result = command_json_result(cmd, timeout + 5 if probe_model else timeout)
    result["checked"] = True
    result["probe"] = probe_model
    return result


def check_web_tools(check_web_tools_enabled: bool, timeout: int) -> dict[str, Any]:
    if not check_web_tools_enabled:
        return {"checked": False}
    if not shutil.which("openclaw"):
        return {
            "checked": True,
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    base_cmd = [
        "openclaw",
        "infer",
        "web",
        "search",
        "--query",
        "Morning Report readiness check",
        "--limit",
        "1",
        "--json",
    ]
    search = command_json_result(base_cmd + ["--provider", PRIMARY_SEARCH_PROVIDER], timeout)
    if search.get("ok"):
        return {
            "checked": True,
            "ok": True,
            "primary_provider": PRIMARY_SEARCH_PROVIDER,
            "fallback_provider": FALLBACK_SEARCH_PROVIDER,
            "fallback_used": False,
            "search": search,
        }
    fallback_search = command_json_result(base_cmd + ["--provider", FALLBACK_SEARCH_PROVIDER], timeout)
    return {
        "checked": True,
        "ok": bool(fallback_search.get("ok")),
        "primary_provider": PRIMARY_SEARCH_PROVIDER,
        "fallback_provider": FALLBACK_SEARCH_PROVIDER,
        "fallback_used": bool(fallback_search.get("ok")),
        "search": search,
        "fallback_search": fallback_search,
    }


def channel_probe_ok(result: dict[str, Any]) -> bool:
    if not result.get("ok"):
        return False
    text_parts = [str(result.get("stdout", "")), str(result.get("stderr", ""))]
    if "json" in result:
        text_parts.append(json.dumps(result["json"], ensure_ascii=False))
    combined = "\n".join(text_parts).lower()
    failure_markers = [
        "probe failed",
        "audit failed",
        "not configured",
        "disabled",
        "secret unavailable",
        "credential unavailable",
        "gatewaysecretrefunavailableerror",
        "error",
    ]
    success_markers = ["works", "probe ok", "audit ok", "\"ok\": true", '"healthy": true']
    if any(marker in combined for marker in failure_markers):
        return False
    if any(marker in combined for marker in success_markers):
        return True
    return False


def check_channel_status(check_channel_status_enabled: bool, timeout: int) -> dict[str, Any]:
    if not check_channel_status_enabled:
        return {"checked": False}
    if not shutil.which("openclaw"):
        return {
            "checked": True,
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    result = command_json_result(
        [
            "openclaw",
            "channels",
            "status",
            "--channel",
            "telegram",
            "--probe",
            "--json",
            "--timeout",
            str(timeout * 1000),
        ],
        timeout + 5,
    )
    result["checked"] = True
    result["ok"] = channel_probe_ok(result)
    return result


def check_model_fallbacks(check_fallbacks: bool, timeout: int) -> dict[str, Any]:
    if not check_fallbacks:
        return {"checked": False}
    if not shutil.which("openclaw"):
        return {
            "checked": True,
            "ok": False,
            "error": "openclaw CLI not found on PATH",
        }
    result = command_json_result(["openclaw", "models", "fallbacks", "list", "--json"], timeout)
    result["checked"] = True
    fallback_count = None
    data = result.get("json")
    if isinstance(data, list):
        fallback_count = len(data)
    elif isinstance(data, dict):
        for key in ["fallbacks", "models", "items"]:
            value = data.get(key)
            if isinstance(value, list):
                fallback_count = len(value)
                break
    result["fallback_count"] = fallback_count
    return result


def check_audio_runtime(check_tts: bool, timeout: int, language: str | None) -> dict[str, Any]:
    requested_lang = (language or "English").strip() or "English"
    language_check = resolve_tts_language(requested_lang)
    result: dict[str, Any] = {
        "curl": {"ok": bool(shutil.which("curl")), "path": shutil.which("curl")},
        "ffmpeg": {
            "ok": bool(shutil.which("ffmpeg")),
            "path": shutil.which("ffmpeg"),
        },
        "google_tts": {
            "checked": False,
            "requested_lang": requested_lang,
            "lang": language_check.get("lang"),
            "status": language_check.get("status"),
            "test_text": language_check.get("test_text"),
        },
    }
    if not check_tts:
        return result

    result["google_tts"] = check_google_tts_language(requested_lang, timeout)
    return result


def run_tools_phase(
    *,
    timeout: int,
    no_cli: bool,
    check_model_enabled: bool,
    probe_model_enabled: bool,
    check_web_tools_enabled: bool,
    check_channel_status_enabled: bool,
    check_fallbacks_enabled: bool,
    check_tts_enabled: bool,
    tts_language: str | None,
) -> ToolReadiness:
    checks: dict[str, Any] = {
        "audio_runtime": check_audio_runtime(check_tts_enabled, timeout, tts_language),
    }

    if no_cli:
        checks["model_runtime"] = {"checked": False, "skipped": True}
        checks["web_tools"] = {"checked": False, "skipped": True}
        checks["channel_status"] = {"checked": False, "skipped": True}
        checks["model_fallbacks"] = {"checked": False, "skipped": True}
    else:
        checks["model_runtime"] = check_model_runtime(
            check_model_enabled,
            probe_model_enabled,
            timeout,
        )
        checks["web_tools"] = check_web_tools(check_web_tools_enabled, timeout)
        checks["channel_status"] = check_channel_status(
            check_channel_status_enabled,
            timeout,
        )
        checks["model_fallbacks"] = check_model_fallbacks(
            check_fallbacks_enabled,
            timeout,
        )

    problems: list[str] = []
    warnings: list[str] = []

    if not no_cli:
        if check_model_enabled and not checks["model_runtime"].get("ok"):
            problems.append("model_runtime_unavailable")
        if check_web_tools_enabled and not checks["web_tools"].get("search", {}).get("ok"):
            problems.append("web_search_unavailable")
        if check_channel_status_enabled and not checks["channel_status"].get("ok"):
            problems.append("telegram_channel_status_unverified")

    google_tts = checks["audio_runtime"]["google_tts"]
    if check_tts_enabled and google_tts.get("status") in {"missing_language", "unsupported_language"}:
        warnings.append("google_tts_language_unsupported")
    elif check_tts_enabled and not google_tts.get("ok"):
        warnings.append("google_tts_unavailable")
    if check_fallbacks_enabled:
        fallback_check = checks["model_fallbacks"]
        if not fallback_check.get("ok"):
            warnings.append("model_fallback_status_unverified")
        elif fallback_check.get("fallback_count") == 0:
            warnings.append("model_fallback_missing")
    if not checks["audio_runtime"]["curl"].get("ok"):
        warnings.append("curl_missing_using_urllib_fallback")
    if not checks["audio_runtime"]["ffmpeg"].get("ok"):
        warnings.append("ffmpeg_missing_using_binary_mp3_append_fallback")
        warnings.append("ffmpeg_missing_speed_adjustment_unavailable")

    return ToolReadiness(problems=problems, warnings=warnings)
