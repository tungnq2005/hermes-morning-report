import sys
import json
import subprocess
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from report_style import normalize_report_style, suggest_report_style  # noqa: E402


class StyleUtilsTests(unittest.TestCase):
    def test_structural_aliases_normalize_to_canonical_styles(self):
        self.assertEqual(normalize_report_style("quick"), "concise")
        self.assertEqual(normalize_report_style("deep-analysis"), "deep_analysis")
        self.assertEqual(normalize_report_style("opportunities/risks"), "opportunities_risks")

    def test_unknown_style_suggests_concise_but_requires_confirmation(self):
        suggestion = suggest_report_style("story mode")

        self.assertEqual(suggestion["canonical"], "concise")
        self.assertFalse(suggestion["recognized"])
        self.assertTrue(suggestion["fallback_used"])
        self.assertTrue(suggestion["needs_confirmation"])

    def test_known_style_does_not_require_extra_fallback_confirmation(self):
        suggestion = suggest_report_style("brief")

        self.assertEqual(suggestion["canonical"], "concise")
        self.assertTrue(suggestion["recognized"])
        self.assertFalse(suggestion["fallback_used"])
        self.assertFalse(suggestion["needs_confirmation"])

    def test_cli_suggests_concise_for_unknown_style(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SKILL_DIR / "scripts" / "report_style.py"),
                "--suggest",
                "story mode",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)

        self.assertEqual(data["canonical"], "concise")
        self.assertTrue(data["needs_confirmation"])


if __name__ == "__main__":
    unittest.main()
