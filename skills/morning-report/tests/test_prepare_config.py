"""Tests for prepare_config.py topic updates."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from prepare_config import (
    build_cron_control_command,
    control_cron,
    find_morning_report_job,
    render_prepare_output,
)

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def complete_config(**overrides):
    data = {
        "topic": "Gold",
        "delivery_time": "07:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "report_style": "concise",
        "report_language": "Vietnamese",
        "audio_summary": "Enabled",
        "delivery_channel": "Telegram",
    }
    data.update(overrides)
    return data


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_add_topic_keeps_existing_topic():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = render_prepare_output(path, {"add_topics": ["AI"]})
        assert result["configured"] is True
        assert result["available_config"]["topics"] == ["Gold", "AI"]
        assert result["missing_config"] == []


def test_remove_topic_marks_topics_missing_when_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config(topics=["Gold"], topic=None))
        result = render_prepare_output(path, {"remove_topics": ["Gold"]})
        assert result["configured"] is False
        assert "topics" in result["missing_config"]


def test_save_migrates_legacy_topic_to_topics():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = render_prepare_output(path, {"add_topics": ["AI"]}, save=True)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert result["configured"] is True
        assert saved["topics"] == ["Gold", "AI"]
        assert "topic" not in saved


SAMPLE_CRON_LIST_ACTIVE = (
    "\n  6ffa54ec332b [active]\n"
    "    Name:      Morning Report\n"
    "    Schedule:  0 1 * * *\n"
)
SAMPLE_CRON_LIST_PAUSED = (
    "\n  6ffa54ec332b [paused]\n"
    "    Name:      Morning Report\n"
    "    Schedule:  0 1 * * *\n"
)
SAMPLE_CRON_LIST_OTHER = (
    "\n  abcdef123456 [active]\n"
    "    Name:      Other Job\n"
    "    Schedule:  0 0 * * *\n"
)


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_build_pause_command():
    assert build_cron_control_command("6ffa54ec332b", "pause") == [
        "hermes", "cron", "--accept-hooks", "pause", "6ffa54ec332b"
    ]


def test_build_resume_command():
    assert build_cron_control_command("6ffa54ec332b", "resume") == [
        "hermes", "cron", "--accept-hooks", "resume", "6ffa54ec332b"
    ]


def test_build_command_rejects_unknown_action():
    raised = False
    try:
        build_cron_control_command("6ffa54ec332b", "delete")
    except ValueError:
        raised = True
    assert raised


def test_find_job_detects_active_state():
    assert find_morning_report_job(SAMPLE_CRON_LIST_ACTIVE) == ("6ffa54ec332b", "active")


def test_find_job_detects_paused_state():
    assert find_morning_report_job(SAMPLE_CRON_LIST_PAUSED) == ("6ffa54ec332b", "paused")


def test_find_job_returns_none_when_missing():
    assert find_morning_report_job(SAMPLE_CRON_LIST_OTHER) is None


def test_control_cron_no_job():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron("pause", path, list_output=SAMPLE_CRON_LIST_OTHER)
        assert result["cron_state"] == "no_job"
        assert "next_action" in result


def test_control_cron_already_paused():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron("pause", path, list_output=SAMPLE_CRON_LIST_PAUSED)
        assert result["cron_state"] == "already_paused"


def test_control_cron_already_running():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron("resume", path, list_output=SAMPLE_CRON_LIST_ACTIVE)
        assert result["cron_state"] == "already_running"


def test_control_cron_pause_success():
    calls = []

    def runner(job_id, action):
        calls.append((job_id, action))
        return _completed(0)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron(
            "pause", path, list_output=SAMPLE_CRON_LIST_ACTIVE, run_control=runner
        )
        assert result["cron_state"] == "paused"
        assert calls == [("6ffa54ec332b", "pause")]


def test_control_cron_resume_success():
    def runner(job_id, action):
        return _completed(0)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron(
            "resume", path, list_output=SAMPLE_CRON_LIST_PAUSED, run_control=runner
        )
        assert result["cron_state"] == "resumed"


def test_control_cron_command_failure_reports_error():
    def runner(job_id, action):
        return _completed(1, stderr="nope")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron(
            "pause", path, list_output=SAMPLE_CRON_LIST_ACTIVE, run_control=runner
        )
        assert result["cron_state"] == "error"


def test_control_cron_skips_real_call_for_non_default_state():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, complete_config())
        result = control_cron("pause", path)
        assert result["cron_state"] == "not_default_state"


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
