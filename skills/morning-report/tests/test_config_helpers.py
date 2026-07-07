import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = SKILL_DIR / "scripts" / "update_config.py"
STATUS_SCRIPT = SKILL_DIR / "scripts" / "config_status.py"


class ConfigHelperTests(unittest.TestCase):
    def test_setup_writes_state_and_user_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            audit = tmp_path / "audit.log"
            user.write_text("# USER\n\nExisting content.\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(UPDATE_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--audit-log",
                    str(audit),
                    "setup",
                    "--topic",
                    "Vietnam real estate",
                    "--delivery-time",
                    "7:00 AM",
                    "--timezone",
                    "Asia/Ho_Chi_Minh",
                    "--report-style",
                    "Concise",
                    "--report-language",
                    "English",
                    "--audio-summary",
                    "Enabled",
                    "--delivery-channel",
                    "Telegram",
                    "--user-status",
                    "enabled",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            status = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--check",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(status.stdout)

            self.assertTrue(data["configured"])
            self.assertEqual(data["missing_required"], [])
            self.assertEqual(data["setup_action"]["type"], "config_ready")
            self.assertTrue(data["setup_action"]["can_continue"])
            self.assertEqual(data["state"]["active_topics"], ["Vietnam real estate"])
            self.assertEqual(data["state"]["report_preferences"]["Report style"], "concise")
            self.assertEqual(data["state"]["report_style"]["canonical"], "concise")
            self.assertEqual(data["user"]["morning_report_preferences"]["Status"], "enabled")
            self.assertEqual(data["user"]["morning_report_preferences"]["Report style"], "concise")
            self.assertIn("Existing content.", user.read_text(encoding="utf-8"))
            audit_records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(audit_records[-1]["action"], "config_updated")

    def test_status_check_fails_when_required_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            state.write_text(
                "# Current Topics\n\n"
                "## Setup status\n\n"
                "Status: not_configured\n\n"
                "## Active topics\n\n"
                "None provided.\n",
                encoding="utf-8",
            )
            user.write_text("# USER\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--check",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertFalse(data["configured"])
            self.assertIn("Status: configured", data["missing_required"])
            self.assertIn("Active topics", data["missing_required"])

    def test_missing_state_file_is_treated_as_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            user.write_text("# USER\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--check",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertFalse(data["configured"])
            self.assertFalse(data["state"]["exists"])
            self.assertEqual(data["setup_action"]["type"], "collect_missing_config")
            self.assertIn("topics", data["setup_action"]["missing_fields"])
            self.assertIn("delivery_time", data["setup_action"]["missing_fields"])
            self.assertIn("audio_summary", data["setup_action"]["defaults"])
            self.assertEqual(data["state"]["setup_status"], "not_configured")
            self.assertIn("state_file", data["missing_required"])
            self.assertIn("Status: configured", data["missing_required"])

    def test_setup_action_uses_user_preferences_before_asking_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            user.write_text(
                "# USER\n\n"
                "- **Timezone:** Asia/Ho_Chi_Minh (GMT+7)\n\n"
                "## Morning Report Preferences\n\n"
                "- Status: enabled\n"
                "- Topics: Vietnam real estate\n"
                "- Delivery time: 7:00 AM\n"
                "- Timezone: Asia/Ho_Chi_Minh (GMT+7)\n"
                "- Report style: Concise\n"
                "- Report language: English\n"
                "- Audio summary: Enabled\n"
                "- Delivery channel: Telegram\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            data = json.loads(result.stdout)
            self.assertFalse(data["configured"])
            self.assertEqual(data["setup_action"]["type"], "confirm_known_config_before_save")
            self.assertEqual(data["setup_action"]["missing_fields"], [])
            self.assertEqual(data["setup_action"]["known_fields"]["topics"], ["Vietnam real estate"])

    def test_status_check_fails_when_report_style_is_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            state.write_text(
                "# Current Topics\n\n"
                "## Setup status\n\n"
                "Status: configured\n\n"
                "## Active topics\n\n"
                "1. AI agents\n\n"
                "## Optional topics\n\n"
                "None provided.\n\n"
                "## User priority\n\n"
                "1. AI agents\n\n"
                "## Report preferences\n\n"
                "- Delivery time: 7:00 AM\n"
                "- Timezone: Asia/Ho_Chi_Minh\n"
                "- Report style: story mode\n"
                "- Report language: English\n"
                "- Audio summary: Disabled\n"
                "- Delivery channel: Telegram\n",
                encoding="utf-8",
            )
            user.write_text("# USER\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(state),
                    "--user",
                    str(user),
                    "--check",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertFalse(data["configured"])
            self.assertFalse(data["state"]["report_style"]["valid"])
            self.assertIn("supported Report style", data["missing_required"])
            self.assertTrue(any("unsupported_report_style" in item for item in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
