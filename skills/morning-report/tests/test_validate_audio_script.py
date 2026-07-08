import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "report" / "validate_audio_script.py"


class ValidateAudioTests(unittest.TestCase):
    def run_validator(self, text: str, *args: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            text_file = Path(tmp) / "audio.txt"
            text_file.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--text-file", str(text_file), *args],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_valid_script_passes_word_count_and_hygiene(self):
        # 620 words sits inside the 600-930 default band, which maps to the
        # contracted 3-5 minute MP3 at the measured 189 wpm delivery rate.
        text = " ".join(f"word{i}" for i in range(620))
        result = self.run_validator(text)
        data = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["word_count"], 620)
        self.assertEqual(data["issues"], [])

    def test_word_count_band_matches_three_to_five_minute_contract(self):
        just_under = self.run_validator(" ".join(f"word{i}" for i in range(599)))
        self.assertNotEqual(just_under.returncode, 0)
        self.assertIn("under_min_words", [i["code"] for i in json.loads(just_under.stdout)["issues"]])

        just_over = self.run_validator(" ".join(f"word{i}" for i in range(931)))
        self.assertNotEqual(just_over.returncode, 0)
        self.assertIn("over_max_words", [i["code"] for i in json.loads(just_over.stdout)["issues"]])

        # 600 words / 189 wpm = 3.17 min; 930 / 189 = 4.92 min -- both inside 3-5.
        low = json.loads(self.run_validator(" ".join(f"word{i}" for i in range(600))).stdout)
        high = json.loads(self.run_validator(" ".join(f"word{i}" for i in range(930))).stdout)
        self.assertGreaterEqual(low["estimated_minutes"], 3.0)
        self.assertLessEqual(high["estimated_minutes"], 5.0)

    def test_short_script_fails(self):
        result = self.run_validator("too short")
        data = json.loads(result.stdout)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(data["ok"])
        self.assertIn("under_min_words", [issue["code"] for issue in data["issues"]])

    def test_hygiene_failures_are_reported(self):
        text = (
            " ".join(f"word{i}" for i in range(620))
            + " Source: Example. https://example.com MEDIA:/tmp/morning-report.mp3 "
            + "This shockingly surged after ffmpeg wrote manifest.json."
        )
        result = self.run_validator(text)
        data = json.loads(result.stdout)
        codes = {issue["code"] for issue in data["issues"]}

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("url_present", codes)
        self.assertIn("media_directive_present", codes)
        self.assertIn("source_label_present", codes)
        self.assertIn("debug_text_present", codes)
        self.assertIn("hype_language_present", codes)

    def test_no_fail_reports_issues_but_exits_zero(self):
        result = self.run_validator("too short", "--no-fail")
        data = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
