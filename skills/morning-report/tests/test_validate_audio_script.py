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
        text = " ".join(f"word{i}" for i in range(560))
        result = self.run_validator(text)
        data = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(data["ok"])
        self.assertEqual(data["word_count"], 560)
        self.assertEqual(data["issues"], [])

    def test_short_script_fails(self):
        result = self.run_validator("too short")
        data = json.loads(result.stdout)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(data["ok"])
        self.assertIn("under_min_words", [issue["code"] for issue in data["issues"]])

    def test_hygiene_failures_are_reported(self):
        text = (
            " ".join(f"word{i}" for i in range(560))
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
