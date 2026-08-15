"""Tests for helpers/history.py — record_audio_validation keeps the audio filename."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from helpers.history import record_audio_validation, load_manifest

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


def _fake_audio(path: Path, size: int = 300):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"a" * size)
    return path


def test_record_audio_keeps_per_topic_basename():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        src = _fake_audio(Path(tmp) / "morning-report-gold.mp3")
        meta = record_audio_validation(run_dir, src)
        assert meta["file"] == "morning-report-gold.mp3"
        assert (run_dir / "morning-report-gold.mp3").exists()
        manifest = load_manifest(run_dir)
        assert manifest["audio"]["file"] == "morning-report-gold.mp3"


def test_record_audio_keeps_default_basename():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        src = _fake_audio(Path(tmp) / "morning-report.mp3")
        meta = record_audio_validation(run_dir, src)
        assert meta["file"] == "morning-report.mp3"


def test_record_audio_copies_into_run_dir_with_its_name():
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        src = _fake_audio(Path(tmp) / "src/morning-report-ai.mp3")
        meta = record_audio_validation(run_dir, src)
        assert (run_dir / "morning-report-ai.mp3").exists()
        assert meta["file"] == "morning-report-ai.mp3"


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
