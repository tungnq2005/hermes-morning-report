"""Tests for check_topic_config.py."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from helpers.check_topic_config import check_topic_config

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_missing_file():
    with tempfile.TemporaryDirectory() as tmp:
        result = check_topic_config(Path(tmp) / "missing.json")
        assert result["configured"] is False
        assert result["available_config"] == {}
        assert "status" not in result["missing_config"]
        assert "topic" in result["missing_config"]


def test_partial_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topic": "AI"})
        result = check_topic_config(path)
        assert result["configured"] is False
        assert result["available_config"]["topic"] == "AI"
        assert "delivery_time" in result["missing_config"]


def test_complete_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(
            path,
            {
                "topic": "AI",
                "delivery_time": "07:00",
                "timezone": "Asia/Ho_Chi_Minh",
                "report_style": "concise",
                "report_language": "Vietnamese",
                "audio_summary": "Enabled",
                "delivery_channel": "Telegram",
            },
        )
        result = check_topic_config(path)
        assert result["configured"] is True
        assert result["missing_config"] == []
        assert result["available_config"]["report_style"] == "concise"


def test_invalid_report_style_is_missing_report_style():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(
            path,
            {
                "topic": "AI",
                "delivery_time": "07:00",
                "timezone": "Asia/Ho_Chi_Minh",
                "report_style": "unknown style",
                "report_language": "Vietnamese",
                "audio_summary": "Enabled",
                "delivery_channel": "Telegram",
            },
        )
        result = check_topic_config(path)
        assert result["configured"] is False
        assert "report_style" in result["missing_config"]
        assert result["available_config"]["report_style"] == "unknown style"


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
