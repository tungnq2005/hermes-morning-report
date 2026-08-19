"""Tests for validate.py --type audio — cleanliness checks and the validated-report gate."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate import validate_audio, check_report_gate
from helpers.history import record_report_validation

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


REPORT = """# Bản tin sáng

## Điểm chính
- Giá vàng đóng cửa ở mức $2,410 một ounce.

### Nguồn
- reuters.com
"""


def _script(words=700):
    return " ".join(["Giá vàng tăng nhẹ trong phiên hôm nay."] * (words // 8))


def _run_dir(tmp, validated=True):
    """A run directory in the state Step 3 leaves behind."""
    run_dir = Path(tmp) / "run-2026-08-20"
    run_dir.mkdir(parents=True)
    report = run_dir / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    record_report_validation(run_dir, report, ok=validated)
    return run_dir


# ── The gate ───────────────────────────────────────────────────────────
def test_validated_report_opens_the_gate():
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_audio(_script(), 680, 930, 150, run_dir=_run_dir(tmp))
        assert result["report_gate"] == "pass", result
        assert result["ok"], result["issues"]


def test_failed_report_blocks_audio():
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_audio(_script(), 680, 930, 150, run_dir=_run_dir(tmp, validated=False))
        assert not result["ok"]
        assert result["report_gate"] == "fail"
        assert [i["code"] for i in result["issues"]] == ["report_not_validated"]


def test_no_manifest_at_all_blocks_audio():
    """The 15/08 shape: an audio script produced without a report run behind it."""
    with tempfile.TemporaryDirectory() as tmp:
        empty = Path(tmp) / "run-empty"
        empty.mkdir()
        result = validate_audio(_script(), 680, 930, 150, run_dir=empty)
        assert not result["ok"]
        assert result["issues"][0]["code"] == "report_not_validated"


def test_report_edited_after_validation_blocks_audio():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_dir(tmp)
        (run_dir / "report.md").write_text(REPORT + "\n- Một dòng thêm vào sau khi validate.\n", encoding="utf-8")
        result = validate_audio(_script(), 680, 930, 150, run_dir=run_dir)
        assert not result["ok"]
        assert result["issues"][0]["code"] == "report_changed_after_validation"


def test_deleted_report_blocks_audio():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _run_dir(tmp)
        (run_dir / "report.md").unlink()
        result = validate_audio(_script(), 680, 930, 150, run_dir=run_dir)
        assert not result["ok"]
        assert result["issues"][0]["code"] == "report_file_missing"


def test_omitting_run_dir_is_not_a_way_around_the_gate():
    result = validate_audio(_script(), 680, 930, 150)
    assert not result["ok"]
    assert result["report_gate"] == "fail"
    assert result["issues"][0]["code"] == "run_dir_required"


def test_skip_flag_is_explicit_and_visible_in_the_output():
    """TTS testing needs a way through, but the output has to say the gate was skipped."""
    result = validate_audio(_script(), 680, 930, 150, skip_report_gate=True)
    assert result["ok"], result["issues"]
    assert result["report_gate"] == "skipped"


def test_gate_reports_no_issues_for_a_clean_run():
    with tempfile.TemporaryDirectory() as tmp:
        assert check_report_gate(_run_dir(tmp)) == []


# ── Script cleanliness (uncovered since the Hermes rewrite) ────────────
def test_short_script_fails_on_word_count():
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_audio("Xin chào.", 680, 930, 150, run_dir=_run_dir(tmp))
        assert not result["ok"]
        assert "under_min_words" in [i["code"] for i in result["issues"]]
        assert result["report_gate"] == "pass", "a short script is not a gate failure"


def test_urls_are_rejected_in_spoken_text():
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_audio(_script() + " Xem tại https://reuters.com nhé.", 680, 930, 150,
                                run_dir=_run_dir(tmp))
        assert "url_present" in [i["code"] for i in result["issues"]]


def test_estimated_minutes_follows_wpm():
    result = validate_audio(_script(720), 0, 0, 150, skip_report_gate=True)
    assert result["estimated_minutes"] == round(result["word_count"] / 150, 2)


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
