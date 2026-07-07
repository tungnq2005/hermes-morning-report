import json
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "report" / "generate_audio_file.py"


def load_generate_audio_module():
    spec = importlib.util.spec_from_file_location("report_audio_for_tests", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load report/generate_audio_file.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenerateAudioTests(unittest.TestCase):
    def run_audio(self, text: str, *args: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "audio.txt"
            text_file.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--text-file", str(text_file), "--dry-run", *args],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)

    def test_dry_run_splits_under_chunk_limit(self):
        data = self.run_audio(
            "Chao buoi sang. "
            "Thi truong bat dong san Viet Nam co nhieu tin hieu can theo doi, "
            "bao gom nguon cung, tin dung, ha tang va thanh khoan thuc te. "
            "Nguoi mua nen kiem tra phap ly du an truoc khi quyet dinh.",
            "--chunk-limit",
            "80",
            "--lang",
            "vi",
        )

        self.assertTrue(data["success"])
        self.assertGreater(data["chunk_count"], 1)
        self.assertTrue(all(len(chunk) <= 80 for chunk in data["chunks"]))
        self.assertFalse(data["length_ok"])
        self.assertTrue(any(item.startswith("under_min_words") for item in data["length_warnings"]))

    def test_language_alias_maps_english_to_en(self):
        data = self.run_audio(
            "Good morning. This is a short audio summary.",
            "--lang",
            "English",
        )

        self.assertEqual(data["requested_lang"], "English")
        self.assertEqual(data["lang"], "en")

    def test_unsupported_language_fails_without_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "audio.txt"
            text_file.write_text("Good morning. This is a short audio summary.", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--text-file", str(text_file), "--dry-run", "--lang", "Klingon"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported_tts_language", result.stderr)

    def test_length_metadata_reports_target_range(self):
        text = " ".join(f"word{i}" for i in range(460))
        data = self.run_audio(text, "--lang", "English", "--min-words", "450", "--max-words", "750")

        self.assertEqual(data["word_count"], 460)
        self.assertEqual(data["target_min_words"], 450)
        self.assertEqual(data["target_max_words"], 750)
        self.assertTrue(data["length_ok"])
        self.assertEqual(data["length_warnings"], [])

    def test_dry_run_reports_requested_speed(self):
        data = self.run_audio(
            " ".join(f"word{i}" for i in range(560)),
            "--lang",
            "English",
            "--speed",
            "1.2",
            "--min-words",
            "540",
            "--max-words",
            "900",
            "--wpm",
            "180",
        )

        self.assertEqual(data["speed"], 1.2)
        self.assertIn("speed_supported", data)
        self.assertEqual(data["speed_supported"], shutil.which("ffmpeg") is not None)
        self.assertFalse(data["speed_applied"])
        self.assertEqual(data["words_per_minute"], 180)
        self.assertTrue(data["length_ok"])

    def test_language_is_required_to_avoid_implicit_voice_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "audio.txt"
            text_file.write_text("Good morning. This is a short audio summary.", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--text-file", str(text_file), "--dry-run"],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--lang", result.stderr)

    def test_speed_adjustment_replaces_final_audio_without_retained_duplicate(self):
        module = load_generate_audio_module()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            audio_file = run_dir / "morning-report.mp3"
            audio_file.write_bytes(b"original" * 40)

            def fake_run(cmd, capture_output, text, check):
                Path(cmd[-1]).write_bytes(b"adjusted" * 40)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(module.shutil, "which", return_value="/usr/bin/ffmpeg"):
                with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                    info = module.apply_audio_speed(audio_file, 1.2, run_dir)

            self.assertTrue(info["speed_applied"])
            self.assertNotIn("speed_adjusted_file", info)
            self.assertEqual(audio_file.read_bytes(), b"adjusted" * 40)
            self.assertFalse((run_dir / "morning-report-speed-adjusted.mp3").exists())
            self.assertFalse((run_dir / ".morning-report-speed-adjusted.tmp.mp3").exists())


if __name__ == "__main__":
    unittest.main()
