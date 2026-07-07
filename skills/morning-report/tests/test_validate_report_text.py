import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "report" / "validate_report_text.py"


class ValidateReportTests(unittest.TestCase):
    def run_validator(self, report: str, style: str = "concise") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            report_file = Path(tmp) / "report.md"
            report_file.write_text(report, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(SCRIPT), "--report-file", str(report_file), "--style", style],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_concise_report_passes_basic_structure(self):
        report = (
            "# Morning Brief — Test\n\n"
            "## Snapshot\n"
            "- One important update.\n\n"
            "## Key updates\n"
            "- Update one with [evidence](https://example.com/1).\n"
            "- Update two with [evidence](https://example.com/2).\n"
            "- Update three with [evidence](https://example.com/3).\n\n"
            "## Watch next\n"
            "- Signal one.\n"
        )
        result = self.run_validator(report)
        data = json.loads(result.stdout)

        self.assertEqual(result.returncode, 0)
        self.assertTrue(data["ok"])

    def test_report_with_internal_text_fails(self):
        result = self.run_validator(
            "# Morning Brief — Test\n\n"
            "## Snapshot\n"
            "- Topic Plan should not appear.\n"
        )
        data = json.loads(result.stdout)
        codes = {issue["code"] for issue in data["issues"]}

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("internal_text_present", codes)
        self.assertIn("too_few_sections", codes)


if __name__ == "__main__":
    unittest.main()
