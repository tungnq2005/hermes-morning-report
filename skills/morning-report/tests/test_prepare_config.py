"""Tests for prepare_config.py (per-topic config + cron reconcile)."""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from prepare_config import (
    apply_requested_config,
    build_cron_control_command,
    control_cron,
    cron_job_name_for_topic,
    cron_prompt_for_topic,
    find_morning_report_jobs,
    hermes_config_timezone,
    hermes_effective_timezone,
    local_time_to_cron,
    render_prepare_output,
    requested_review,
    sync_cron_jobs,
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


def topic_obj(name="AI", **overrides):
    obj = {
        "topic": name,
        "delivery_time": "08:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "report_style": "concise",
        "report_language": "English",
        "audio_summary": "Enabled",
        "delivery_channel": "Telegram",
    }
    obj.update(overrides)
    return obj


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


SAMPLE_LIST = (
    "\n  6ffa54ec332b [active]\n    Name:      Morning Report\n    Schedule:  0 1 * * *\n"
    "\n  aabbccdd1122 [active]\n    Name:      Morning Report - AI\n    Schedule:  0 1 * * *\n"
    "\n  aabbccdd2233 [paused]\n    Name:      Morning Report - Gold\n    Schedule:  0 1 * * *\n"
    "\n  abcdef998877 [active]\n    Name:      Other Job\n    Schedule:  0 0 * * *\n"
)


# ── apply_requested_config ──
def test_apply_add_topic_inherits_defaults():
    data = {"topics": [topic_obj("Gold", report_style="deep_analysis")]}
    candidate = apply_requested_config(data, {"add_topics": ["AI"]})
    assert [t["topic"] for t in candidate["topics"]] == ["Gold", "AI"]
    ai = next(t for t in candidate["topics"] if t["topic"] == "AI")
    assert ai["report_style"] == "deep_analysis"


def test_apply_add_topic_uses_defaults_when_empty():
    candidate = apply_requested_config({"topics": []}, {"add_topics": ["AI"]})
    assert [t["topic"] for t in candidate["topics"]] == ["AI"]
    assert candidate["topics"][0]["delivery_time"] == "08:00"


def test_apply_remove_topic():
    data = {"topics": [topic_obj("Gold"), topic_obj("AI")]}
    candidate = apply_requested_config(data, {"remove_topics": ["Gold"]})
    assert [t["topic"] for t in candidate["topics"]] == ["AI"]


def test_apply_change_one_topic_field():
    data = {"topics": [topic_obj("Gold"), topic_obj("AI")]}
    candidate = apply_requested_config(data, {"topic": "AI", "report_style": "deep_analysis"})
    ai = next(t for t in candidate["topics"] if t["topic"] == "AI")
    gold = next(t for t in candidate["topics"] if t["topic"] == "Gold")
    assert ai["report_style"] == "deep_analysis"
    assert gold["report_style"] == "concise"


def test_apply_all_topics_field():
    data = {"topics": [topic_obj("Gold"), topic_obj("AI")]}
    candidate = apply_requested_config(data, {"all_topics": True, "timezone": "UTC"})
    assert all(t["timezone"] == "UTC" for t in candidate["topics"])


def test_apply_change_nonexistent_topic_no_effect():
    data = {"topics": [topic_obj("AI")]}
    candidate = apply_requested_config(data, {"topic": "Nope", "report_style": "deep_analysis"})
    assert candidate["topics"][0]["report_style"] == "concise"


# ── requested_review ──
def test_review_change_one_topic_bullet():
    data = {"topics": [topic_obj("AI", report_style="concise")]}
    req = {"topic": "AI", "report_style": "deep_analysis"}
    candidate = apply_requested_config(data, req)
    bullets, warnings = requested_review(data, candidate, req)
    assert any("AI" in b and "concise → deep_analysis" in b for b in bullets)
    assert warnings == []


def test_review_warning_topic_not_found():
    data = {"topics": [topic_obj("AI")]}
    req = {"topic": "Nope", "report_style": "deep_analysis"}
    candidate = apply_requested_config(data, req)
    bullets, warnings = requested_review(data, candidate, req)
    assert any("Nope" in w for w in warnings)
    assert bullets == []


def test_review_warning_no_target():
    data = {"topics": [topic_obj("AI")]}
    req = {"report_style": "deep_analysis"}
    candidate = apply_requested_config(data, req)
    bullets, warnings = requested_review(data, candidate, req)
    assert any("target" in w for w in warnings)
    assert bullets == []


def test_review_add_and_remove():
    data = {"topics": [topic_obj("Gold"), topic_obj("AI")]}
    req = {"add_topics": ["Crypto"], "remove_topics": ["Gold"]}
    candidate = apply_requested_config(data, req)
    bullets, warnings = requested_review(data, candidate, req)
    assert any("add topic: Crypto" in b for b in bullets)
    assert any("remove topic: Gold" in b for b in bullets)


# ── render_prepare_output ──
def test_render_status_configured():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        result = render_prepare_output(path, {})
        assert result["configured"] is True
        assert result["available_config"]["topics"][0]["topic"] == "AI"
        assert result["requested_changes"] == []


def test_render_save_writes_per_topic_schema():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        render_prepare_output(path, {"topic": "AI", "report_style": "deep_analysis"}, save=True)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert set(saved.keys()) == {"topics"}
        assert saved["topics"][0]["report_style"] == "deep_analysis"


def test_render_save_blocked_when_incomplete():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI", report_style="")]})
        result = render_prepare_output(path, {}, save=True)
        assert result["configured"] is False
        assert "report_style" in result["missing_config"]["AI"]


def test_render_migrates_flat_config_on_status():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {
            "topics": ["AI", "Gold"],
            "delivery_time": "08:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "report_style": "concise",
            "report_language": "English",
            "audio_summary": "Enabled",
            "delivery_channel": "Telegram",
        })
        result = render_prepare_output(path, {})
        assert result["configured"] is True
        names = [t["topic"] for t in result["available_config"]["topics"]]
        assert names == ["AI", "Gold"]
        assert result["available_config"]["topics"][0]["delivery_time"] == "08:00"


# ── cron helpers ──
@contextmanager
def hermes_tz(value):
    """Pin the timezone Hermes would evaluate cron in (HERMES_TIMEZONE wins)."""
    previous = os.environ.get("HERMES_TIMEZONE")
    os.environ["HERMES_TIMEZONE"] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HERMES_TIMEZONE", None)
        else:
            os.environ["HERMES_TIMEZONE"] = previous


def test_local_time_to_cron_utc_host():
    # Hermes on UTC (the Ubuntu VPS): 08:00 Asia/Ho_Chi_Minh (UTC+7) -> 01:00 UTC
    with hermes_tz("UTC"):
        assert local_time_to_cron("08:00", "Asia/Ho_Chi_Minh") == "0 1 * * *"


def test_local_time_to_cron_same_tz_host():
    # Hermes on the customer's own timezone (macOS desktop): no shift at all.
    with hermes_tz("Asia/Ho_Chi_Minh"):
        assert local_time_to_cron("08:00", "Asia/Ho_Chi_Minh") == "0 8 * * *"


def test_local_time_to_cron_cross_tz_host():
    # Topic in ICT, Hermes clock in Tokyo (UTC+9): 08:00 ICT -> 10:00 JST
    with hermes_tz("Asia/Tokyo"):
        assert local_time_to_cron("08:00", "Asia/Ho_Chi_Minh") == "0 10 * * *"


def test_local_time_to_cron_offset():
    # 08:00 + 120 min -> 10:00 ICT -> 03:00 UTC
    with hermes_tz("UTC"):
        assert local_time_to_cron("08:00", "Asia/Ho_Chi_Minh", offset_minutes=120) == "0 3 * * *"


def test_local_time_to_cron_bad_hermes_tz_falls_back_to_local():
    # Fail-open like upstream hermes_time.py: a garbage value must not raise.
    with hermes_tz("Not/AZone"):
        assert local_time_to_cron("08:00", "Asia/Ho_Chi_Minh").endswith("* * *")


def test_local_time_to_cron_rejects_bad_delivery_time():
    for bad in ("8am", "25:00", "08:60", ""):
        try:
            local_time_to_cron(bad, "Asia/Ho_Chi_Minh")
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_hermes_config_timezone_reads_top_level_key():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        cfg.write_text('model: deepseek\ntimezone: "Asia/Ho_Chi_Minh"  # local\n', encoding="utf-8")
        assert hermes_config_timezone(cfg) == "Asia/Ho_Chi_Minh"


def test_hermes_config_timezone_missing_file_or_key():
    with tempfile.TemporaryDirectory() as tmp:
        assert hermes_config_timezone(Path(tmp) / "nope.yaml") == ""
        cfg = Path(tmp) / "config.yaml"
        cfg.write_text("model: deepseek\n", encoding="utf-8")
        assert hermes_config_timezone(cfg) == ""


def test_hermes_effective_timezone_env_beats_config():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.yaml"
        cfg.write_text("timezone: Asia/Tokyo\n", encoding="utf-8")
        with hermes_tz("UTC"):
            assert hermes_effective_timezone(cfg) == "UTC"
        previous = os.environ.pop("HERMES_TIMEZONE", None)
        try:
            assert hermes_effective_timezone(cfg) == "Asia/Tokyo"
        finally:
            if previous is not None:
                os.environ["HERMES_TIMEZONE"] = previous


def test_cron_job_name_for_topic():
    assert cron_job_name_for_topic("AI") == "Morning Report - AI"


def test_cron_prompt_for_topic_contains_topic():
    p = cron_prompt_for_topic("AI")
    assert "AI" in p
    assert "only the topic" in p


# ── find_morning_report_jobs ──
def test_find_jobs_prefix_match():
    jobs = find_morning_report_jobs(SAMPLE_LIST)
    names = sorted(n for _, n, _ in jobs)
    assert names == ["Morning Report", "Morning Report - AI", "Morning Report - Gold"]


def test_find_jobs_states():
    jobs = find_morning_report_jobs(SAMPLE_LIST)
    by_name = {n: s for _, n, s in jobs}
    assert by_name["Morning Report - Gold"] == "paused"
    assert by_name["Morning Report - AI"] == "active"


# ── build_cron_control_command ──
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


# ── control_cron ──
def test_control_cron_no_job():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        other = "\n  abcdef998877 [active]\n    Name:      Other Job\n"
        result = control_cron("pause", path, list_output=other)
        assert result["cron_state"] == "no_job"


def test_control_cron_skips_real_call_for_non_default_state():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        result = control_cron("pause", path)
        assert result["cron_state"] == "not_default_state"


def test_control_cron_pause_all_success():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        calls = []

        def runner(jid, action):
            calls.append((jid, action))
            return _completed(0)

        result = control_cron("pause", path, list_output=SAMPLE_LIST, run_control=runner)
        assert result["cron_state"] == "paused"
        # legacy + AI are active -> paused; Gold already paused -> skipped.
        assert len(calls) == 2


def test_control_cron_already_paused():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})
        all_paused = (
            "\n  aabbccdd1122 [paused]\n    Name:      Morning Report - AI\n"
            "\n  aabbccdd2233 [paused]\n    Name:      Morning Report - Gold\n"
        )

        def runner(jid, action):
            return _completed(0)

        result = control_cron("pause", path, list_output=all_paused, run_control=runner)
        assert result["cron_state"] == "already_paused"


def test_control_cron_partial_error():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        write_json(path, {"topics": [topic_obj("AI")]})

        def runner(jid, action):
            return _completed(1, stderr="nope")

        result = control_cron("pause", path, list_output=SAMPLE_LIST, run_control=runner)
        assert result["cron_state"] == "error"


# ── sync_cron_jobs ──
def test_sync_no_change_returns_empty():
    result = sync_cron_jobs(Path("/tmp/whatever"), [topic_obj("AI")], [topic_obj("AI")], enable_cron=False)
    assert result == ""


def test_sync_non_default_state_guard():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "topic-config.json"
        result = sync_cron_jobs(
            path,
            [topic_obj("AI")],
            [topic_obj("AI", delivery_time="07:00")],
            enable_cron=True,
        )
        assert "not the default config path" in result


def test_sync_reconcile_creates_missing_jobs_and_removes_legacy():
    calls = []

    def runner(args):
        calls.append(args)
        return _completed(0)

    list_out = "\n  6ffa54ec332b [active]\n    Name:      Morning Report\n    Schedule:  0 1 * * *\n"
    result = sync_cron_jobs(
        Path("/tmp/whatever"),
        [],
        [topic_obj("AI"), topic_obj("Gold")],
        enable_cron=True,
        list_output=list_out,
        run_cron=runner,
    )
    creates = [c for c in calls if "create" in c]
    removes = [c for c in calls if "remove" in c]
    assert len(creates) == 2
    assert len(removes) == 1  # legacy single job


def test_sync_reconcile_removes_stale_topic_job():
    calls = []

    def runner(args):
        calls.append(args)
        return _completed(0)

    list_out = (
        "\n  aabbccdd1122 [active]\n    Name:      Morning Report - AI\n    Schedule:  0 1 * * *\n"
        "\n  aabbccdd2233 [active]\n    Name:      Morning Report - Old\n    Schedule:  0 1 * * *\n"
    )
    sync_cron_jobs(
        Path("/tmp/whatever"),
        [topic_obj("AI"), topic_obj("Old")],
        [topic_obj("AI")],
        enable_cron=True,
        list_output=list_out,
        run_cron=runner,
    )
    removes = [c for c in calls if "remove" in c]
    assert len(removes) == 1
    assert "aabbccdd2233" in removes[0]  # Old job removed by its jid


def test_sync_reconcile_edits_schedule():
    calls = []

    def runner(args):
        calls.append(args)
        return _completed(0)

    list_out = "\n  aabbccdd1122 [active]\n    Name:      Morning Report - AI\n    Schedule:  0 1 * * *\n"
    sync_cron_jobs(
        Path("/tmp/whatever"),
        [topic_obj("AI", delivery_time="08:00")],
        [topic_obj("AI", delivery_time="07:00")],
        enable_cron=True,
        list_output=list_out,
        run_cron=runner,
    )
    edits = [c for c in calls if "edit" in c]
    creates = [c for c in calls if "create" in c]
    assert len(edits) == 1
    assert creates == []


def test_sync_schedule_only_edits_existing_without_enable():
    calls = []

    def runner(args):
        calls.append(args)
        return _completed(0)

    list_out = "\n  aabbccdd1122 [active]\n    Name:      Morning Report - AI\n    Schedule:  0 1 * * *\n"
    result = sync_cron_jobs(
        Path("/tmp/whatever"),
        [topic_obj("AI", delivery_time="08:00")],
        [topic_obj("AI", delivery_time="07:00")],
        enable_cron=False,
        list_output=list_out,
        run_cron=runner,
    )
    edits = [c for c in calls if "edit" in c]
    creates = [c for c in calls if "create" in c]
    removes = [c for c in calls if "remove" in c]
    assert len(edits) == 1
    assert creates == []
    assert removes == []


# ── Run ──
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
