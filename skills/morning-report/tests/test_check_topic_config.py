"""Tests for check_topic_config.py (per-topic schema + migration)."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from helpers.check_topic_config import check_topic_config, normalize_config

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def write_json(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def topic_config(name="AI", **overrides):
    obj = {
        "topic": name,
        "delivery_time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "report_style": "concise",
        "report_language": "Vietnamese",
        "audio_summary": "Enabled",
        "delivery_channel": "Telegram",
    }
    obj.update(overrides)
    return obj


# ── missing / empty ──
def test_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        result = check_topic_config(Path(tmp) / "missing.json")
        assert result["configured"] is False
        assert result["available_config"]["topics"] == []
        assert result["missing_config"] == {}


def test_empty_topics_list():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": []})
        result = check_topic_config(path)
        assert result["configured"] is False
        assert result["available_config"]["topics"] == []


# ── per-topic schema ──
def test_complete_single_topic():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_config("AI")]})
        result = check_topic_config(path)
        assert result["configured"] is True
        assert result["missing_config"] == {}
        assert result["available_config"]["topics"][0]["topic"] == "AI"


def test_complete_two_topics():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_config("AI"), topic_config("Gold")]})
        result = check_topic_config(path)
        assert result["configured"] is True
        assert len(result["available_config"]["topics"]) == 2
        assert result["missing_config"] == {}


def test_one_incomplete_topic():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_config("AI"), topic_config("Gold", report_style="")]})
        result = check_topic_config(path)
        assert result["configured"] is False
        assert "Gold" in result["missing_config"]
        assert "report_style" in result["missing_config"]["Gold"]
        assert "AI" not in result["missing_config"]


def test_invalid_report_style_missing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_config("AI", report_style="bogus")]})
        result = check_topic_config(path)
        assert result["configured"] is False
        assert "report_style" in result["missing_config"]["AI"]


# ── migration ──
def test_migrate_flat_string_topics_with_shared_fields():
    flat = {
        "topics": ["AI", "Gold"],
        "delivery_time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "report_style": "concise",
        "report_language": "Vietnamese",
        "audio_summary": "Enabled",
        "delivery_channel": "Telegram",
    }
    norm = normalize_config(flat)
    names = [t["topic"] for t in norm["topics"]]
    assert names == ["AI", "Gold"]
    assert norm["topics"][0]["delivery_time"] == "07:00"
    assert norm["topics"][1]["report_style"] == "concise"


def test_migrate_legacy_single_topic_field():
    legacy = {
        "topic": "AI",
        "delivery_time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "report_style": "concise",
        "report_language": "Vietnamese",
        "audio_summary": "Enabled",
        "delivery_channel": "Telegram",
    }
    norm = normalize_config(legacy)
    assert len(norm["topics"]) == 1
    assert norm["topics"][0]["topic"] == "AI"
    assert norm["topics"][0]["delivery_time"] == "07:00"


def test_migrate_flat_then_check_configured():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {
            "topics": ["AI"],
            "delivery_time": "07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "report_style": "concise",
            "report_language": "Vietnamese",
            "audio_summary": "Enabled",
            "delivery_channel": "Telegram",
        })
        result = check_topic_config(path)
        assert result["configured"] is True
        assert result["available_config"]["topics"][0]["topic"] == "AI"


def test_already_per_topic_schema_preserved():
    data = {"topics": [topic_config("AI", report_language="English")]}
    norm = normalize_config(data)
    assert norm["topics"][0]["report_language"] == "English"
    assert norm["topics"][0]["topic"] == "AI"


def test_migrate_dedup_by_casefold():
    flat = {"topics": ["AI", "ai"], "delivery_time": "07:00", "timezone": "x",
            "report_style": "concise", "report_language": "en",
            "audio_summary": "Enabled", "delivery_channel": "Telegram"}
    norm = normalize_config(flat)
    assert [t["topic"] for t in norm["topics"]] == ["AI"]


def test_config_written_before_google_doc_existed_is_still_complete():
    # An optional field must never turn a working install into "missing config".
    old = {"topics": [{"topic": "AI", "delivery_time": "08:00", "timezone": "Asia/Ho_Chi_Minh",
                       "report_style": "concise", "report_language": "Vietnamese",
                       "audio_summary": "Enabled", "delivery_channel": "Telegram"}]}
    result = check_topic_config(old)
    assert result["configured"] is True, result
    assert result["missing_config"] == {}
    assert result["available_config"]["topics"][0]["google_doc"] == "Disabled"


def test_google_doc_value_is_normalized():
    cfg = {"topics": [{"topic": "AI", "google_doc": "on"}, {"topic": "Gold", "google_doc": "weird"}]}
    topics = normalize_config(cfg)["topics"]
    assert topics[0]["google_doc"] == "Enabled"
    assert topics[1]["google_doc"] == "Disabled"


# ── Run ──
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
