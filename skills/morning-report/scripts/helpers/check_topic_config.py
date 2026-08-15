#!/usr/bin/env python3
"""Check topic-config.json completeness (per-topic) for Morning Report run workflows.

Config schema (per-topic):
    {"topics": [
        {"topic": "<name>", "delivery_time": "...", "timezone": "...",
         "report_style": "...", "report_language": "...",
         "audio_summary": "...", "delivery_channel": "..."},
        ...
    ]}

Legacy flat configs (topics as a string list plus shared preference fields, or a
single "topic" string) are migrated to per-topic objects on read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".hermes/skills/productivity/morning-report/state/topic-config.json"

CANONICAL_STYLES = ("concise", "deep_analysis", "opportunities_risks")

PREFERENCE_FIELDS = [
    "delivery_time",
    "timezone",
    "report_style",
    "report_language",
    "audio_summary",
    "delivery_channel",
]

REQUIRED_TOPIC_FIELDS = ["topic", *PREFERENCE_FIELDS]

# Defaults used when adding a brand-new topic with no existing topic to copy from.
DEFAULT_TOPIC_CONFIG: dict[str, str] = {
    "delivery_time": "08:00",
    "timezone": "Asia/Ho_Chi_Minh",
    "report_style": "concise",
    "report_language": "English",
    "audio_summary": "Enabled",
    "delivery_channel": "Telegram",
}


def normalize_topics(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_topics = [value]
    elif isinstance(value, list):
        raw_topics = value
    else:
        raw_topics = []

    topics: list[str] = []
    seen: set[str] = set()
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, str):
            continue
        topic = raw_topic.strip()
        key = topic.casefold()
        if topic and key not in seen:
            topics.append(topic)
            seen.add(key)
    return topics


def _topic_obj(topic: str, shared: dict[str, Any]) -> dict[str, Any]:
    obj: dict[str, Any] = {"topic": topic}
    for field in PREFERENCE_FIELDS:
        obj[field] = shared.get(field, "")
    return obj


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    """Return config in the per-topic schema {"topics": [ {topic-config}, ... ]}.

    Migrates legacy flat configs (topics as a string list + shared fields, or a
    single legacy "topic" string) into per-topic config objects.
    """
    if not isinstance(data, dict):
        return {"topics": []}

    raw_topics = data.get("topics")
    # Already per-topic schema: topics is a list of config objects.
    if isinstance(raw_topics, list) and raw_topics and isinstance(raw_topics[0], dict):
        topics: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_topics:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            key = topic.casefold()
            if not topic or key in seen:
                continue
            seen.add(key)
            obj: dict[str, Any] = {"topic": topic}
            for field in PREFERENCE_FIELDS:
                obj[field] = item.get(field, "")
            topics.append(obj)
        return {"topics": topics}

    # Legacy/flat: topics is a string list (or legacy "topic" string) + shared fields.
    shared = {field: data.get(field, "") for field in PREFERENCE_FIELDS}
    names = normalize_topics(raw_topics if isinstance(raw_topics, list) else [])
    if not names:
        names = normalize_topics(data.get("topic"))
    return {"topics": [_topic_obj(name, shared) for name in names]}


def check_topic_config(config: Path | dict[str, Any] = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Return configured state plus per-topic available and missing config fields."""
    if isinstance(config, Path):
        path = config
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = config

    normalized = normalize_config(data if isinstance(data, dict) else {})
    topics = normalized["topics"]

    available: list[dict[str, Any]] = []
    missing: dict[str, list[str]] = {}
    for obj in topics:
        topic_name = obj["topic"]
        topic_missing: list[str] = []
        for field in REQUIRED_TOPIC_FIELDS:
            value = obj.get(field)
            if isinstance(value, str):
                value = value.strip()
            if not value:
                topic_missing.append(field)
                continue
            if field == "report_style" and value not in CANONICAL_STYLES:
                topic_missing.append(field)
        if topic_missing:
            missing[topic_name] = topic_missing
        available.append(obj)

    configured = bool(available) and not missing
    return {
        "configured": configured,
        "available_config": {"topics": available},
        "missing_config": missing,
    }
