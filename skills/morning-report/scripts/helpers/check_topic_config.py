#!/usr/bin/env python3
"""Check topic-config.json completeness for Morning Report run workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".hermes/skills/productivity/morning-report/state/topic-config.json"

CANONICAL_STYLES = ("concise", "deep_analysis", "opportunities_risks")

REQUIRED_CONFIG_FIELDS = [
    "topic",
    "delivery_time",
    "timezone",
    "report_style",
    "report_language",
    "audio_summary",
    "delivery_channel",
]


def check_topic_config(
    config: Path | dict[str, Any] = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    """Return configured state plus present and missing config fields."""
    if isinstance(config, Path):
        path = config
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "configured": False,
                "available_config": {},
                "missing_config": list(REQUIRED_CONFIG_FIELDS),
            }
    else:
        data = config

    if not isinstance(data, dict):
        data = {}

    available: dict[str, Any] = {}
    missing: list[str] = []

    for key in REQUIRED_CONFIG_FIELDS:
        value = data.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value:
            available[key] = value
        else:
            missing.append(key)

    report_style = available.get("report_style")
    if report_style and report_style not in CANONICAL_STYLES and "report_style" not in missing:
        missing.append("report_style")

    return {
        "configured": not missing,
        "available_config": available,
        "missing_config": missing,
    }
