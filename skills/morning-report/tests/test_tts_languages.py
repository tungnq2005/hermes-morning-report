import json
import subprocess
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "tts_languages.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import tts_languages  # noqa: E402


class TtsLanguageTests(unittest.TestCase):
    def test_language_maps_are_derived_from_single_source(self):
        self.assertEqual(set(tts_languages.TTS_TEST_TEXTS), set(tts_languages.TTS_LANGUAGES))
        self.assertNotIn("tiếng việt", tts_languages.LANGUAGE_ALIASES)
        self.assertEqual(tts_languages.LANGUAGE_ALIASES["vietnamese"], "vi")

    def test_resolves_supported_language_name(self):
        result = tts_languages.resolve_tts_language("Vietnamese")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "supported_language")
        self.assertEqual(result["lang"], "vi")
        self.assertIn("âm thanh", result["test_text"])

    def test_resolves_direct_language_code(self):
        result = tts_languages.resolve_tts_language("zh-TW")

        self.assertTrue(result["ok"])
        self.assertEqual(result["lang"], "zh-TW")

    def test_unknown_language_is_unsupported_without_guessing(self):
        result = tts_languages.resolve_tts_language("Klingon")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unsupported_language")
        self.assertIsNone(result["lang"])
        self.assertIsNone(result["test_text"])

    def test_cli_returns_json_for_unsupported_language(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--language", "Klingon", "--compact"],
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(result.stdout)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "unsupported_language")
        self.assertNotIn("next_action", data)


if __name__ == "__main__":
    unittest.main()
