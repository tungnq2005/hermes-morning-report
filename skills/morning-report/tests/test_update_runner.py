import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
UPDATE_CONFIG = SKILL_DIR / "scripts" / "update_config.py"
UPDATE_RUNNER = SKILL_DIR / "scripts" / "update" / "run.py"


def write_base_config(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(UPDATE_CONFIG),
            "--state",
            str(tmp_path / "current-topics.md"),
            "--user",
            str(tmp_path / "USER.md"),
            "--audit-log",
            str(tmp_path / "audit.log"),
            "setup",
            "--topic",
            "World Cup 2026",
            "--delivery-time",
            "6:00 AM",
            "--timezone",
            "Asia/Ho_Chi_Minh",
            "--report-style",
            "concise",
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


def run_runner_result(tmp_path: Path, command: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(UPDATE_RUNNER),
            "--state",
            str(tmp_path / "current-topics.md"),
            "--user",
            str(tmp_path / "USER.md"),
            "--audit-log",
            str(tmp_path / "audit.log"),
            "--work-dir",
            str(tmp_path / "update-work"),
            command,
            *args,
        ],
        capture_output=True,
        text=True,
    )


def run_preview_result(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    return run_runner_result(tmp_path, "preview", *args)


def run_runner(tmp_path: Path, command: str, *args: str) -> dict:
    result = run_runner_result(tmp_path, command, *args)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def run_preview(tmp_path: Path, *args: str) -> dict:
    return run_runner(tmp_path, "preview", *args)


class UpdateRunnerTests(unittest.TestCase):
    def test_check_config_is_step_one_without_save_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)

            result = subprocess.run(
                [
                    sys.executable,
                    str(UPDATE_RUNNER),
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--audit-log",
                    str(tmp_path / "audit.log"),
                    "--work-dir",
                    str(tmp_path / "update-work"),
                    "check-config",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            self.assertEqual(data["phase"], "check-config")
            self.assertEqual(data["next_action"]["type"], "preview_update")
            self.assertEqual(data["current_config"]["topics"], ["World Cup 2026"])
            self.assertIn("command_template", data["next_action"])
            self.assertNotIn("save_command", data["next_action"])

    def test_mixed_update_previews_confirmation_and_scheduler_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)

            data = run_preview(
                tmp_path,
                "--replace-topic",
                "Vietnam real estate",
                "--delivery-time",
                "7:00 AM",
                "--report-language",
                "Vietnamese",
            )

            self.assertTrue(data["success"])
            self.assertEqual(data["next_action"]["type"], "confirm_update")
            self.assertIn(" apply ", data["next_action"]["after_confirmation"]["command"])
            self.assertTrue(Path(data["preview_file"]).exists())
            self.assertEqual(data["resulting_config"]["topics"], ["Vietnam real estate"])
            self.assertEqual(data["resulting_config"]["preferences"]["Delivery time"], "7:00 AM")
            changed = {item["field"] for item in data["changed_fields"]}
            self.assertIn("Topics", changed)
            self.assertIn("Delivery time", changed)
            self.assertIn("Report language", changed)

            applied = run_runner(tmp_path, "apply", "--preview-file", data["preview_file"])
            self.assertEqual(applied["next_action"]["type"], "save_update")
            self.assertTrue(applied["next_action"]["scheduler_action_after_save"]["required"])
            self.assertIn(" save ", applied["next_action"]["command"])

            saved = run_runner(tmp_path, "save", "--preview-file", data["preview_file"])
            self.assertTrue(saved["success"])
            self.assertEqual(saved["next_action"]["type"], "verify_scheduler_after_save")

    def test_unclear_style_requires_confirmation_before_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)

            data = run_preview(tmp_path, "--report-style", "morning vibe")

            self.assertTrue(data["success"])
            self.assertFalse(data["can_continue"])
            self.assertEqual(data["next_action"]["type"], "confirm_style")
            self.assertEqual(data["next_action"]["style_suggestion"]["canonical"], "concise")
            self.assertNotIn("save_command", data["next_action"])

    def test_missing_setup_blocks_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            result = run_preview_result(tmp_path, "--replace-topic", "Crypto")
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 2)
            self.assertFalse(data["success"])
            self.assertEqual(data["error"], "setup_required_before_update")

    def test_remove_last_topic_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)

            result = run_preview_result(tmp_path, "--remove-topic", "World Cup 2026")
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 2)
            self.assertFalse(data["success"])
            self.assertEqual(data["error"], "invalid_resulting_config")
            self.assertIn("active_topics_required", data["details"])

    def test_view_only_returns_current_config_without_save_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)

            data = run_preview(tmp_path)

            self.assertEqual(data["next_action"]["type"], "report_no_change")
            self.assertEqual(data["current_config"]["topics"], ["World Cup 2026"])
            self.assertNotIn("save_command", data["next_action"])

    def test_resume_requires_scheduler_verification_before_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            write_base_config(tmp_path)
            subprocess.run(
                [
                    sys.executable,
                    str(UPDATE_CONFIG),
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--audit-log",
                    str(tmp_path / "audit.log"),
                    "set-status",
                    "--status",
                    "paused",
                    "--sync-user",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            data = run_preview(tmp_path, "--status", "configured")

            applied = run_runner(tmp_path, "apply", "--preview-file", data["preview_file"])

            self.assertEqual(applied["next_action"]["type"], "verify_scheduler_before_save")
            self.assertEqual(applied["next_action"]["scheduler_action"]["order"], "verify_scheduler_then_save")
            self.assertIn("command", applied["next_action"]["after_scheduler"])


if __name__ == "__main__":
    unittest.main()
