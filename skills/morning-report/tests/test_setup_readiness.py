import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
SETUP_RUN_SCRIPT = SKILL_DIR / "scripts" / "setup" / "run.py"
UPDATE_SCRIPT = SKILL_DIR / "scripts" / "update_config.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from setup import run as setup_run  # noqa: E402
from setup import common as setup_common  # noqa: E402
from setup import tool_readiness as setup_tools  # noqa: E402


def run_setup_readiness(
    tmp_path: Path,
    *extra_args: str,
    phase: str = "tools",
    check: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SETUP_RUN_SCRIPT),
            phase,
            "--state",
            str(tmp_path / "current-topics.md"),
            "--user",
            str(tmp_path / "USER.md"),
            "--no-cli",
            "--agents-reviewed",
            "--compact",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        check=check,
    )


def assert_agent_contract(testcase: unittest.TestCase, data: dict) -> None:
    testcase.assertEqual(set(data), {"status", "next_action"})
    testcase.assertIsInstance(data["status"], str)
    testcase.assertTrue(data["status"].strip())
    testcase.assertLessEqual(set(data["next_action"]), {"command", "instructions"})
    testcase.assertIsInstance(data["next_action"]["instructions"], list)
    testcase.assertTrue(data["next_action"]["instructions"])


class SetupReadinessTests(unittest.TestCase):
    def test_tools_phase_returns_config_status_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")

            result = run_setup_readiness(tmp_path, check=True)
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0)
            assert_agent_contract(self, data)
            self.assertEqual(data["status"], "Setup readiness checks passed and configuration status can be checked.")
            self.assertIn("config_status.py", data["next_action"]["command"])

    def test_system_phase_returns_tools_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")

            result = run_setup_readiness(tmp_path, phase="system", check=True)
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0)
            assert_agent_contract(self, data)
            self.assertEqual(data["status"], "Setup system phase passed and tool readiness can be checked.")
            self.assertIn("setup/run.py tools", data["next_action"]["command"])

    def test_configured_state_is_ready_when_environment_checks_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(UPDATE_SCRIPT),
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--audit-log",
                    str(tmp_path / "audit.log"),
                    "setup",
                    "--topic",
                    "Indonesia cuisine",
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

            result = run_setup_readiness(tmp_path, "--check", check=True)
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0)
            assert_agent_contract(self, data)

    def test_no_cli_full_readiness_returns_action_only_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")

            result = run_setup_readiness(tmp_path, "--full-readiness", check=True)
            data = json.loads(result.stdout)

            self.assertEqual(result.returncode, 0)
            assert_agent_contract(self, data)
            self.assertNotIn("checks", data)
            self.assertNotIn("phases", data)
            self.assertNotIn("problems", data)
            self.assertNotIn("warnings", data)

    def test_command_result_failure_is_not_agent_log(self):
        result = setup_common.command_result(["/missing/openclaw-command"], 1)

        self.assertFalse(result["ok"])
        self.assertIsInstance(result["error"], str)
        self.assertNotIn("next_action", result)

    def test_web_tools_does_not_probe_cli_fetch(self):
        calls = []

        def fake_json_result(cmd, timeout):
            calls.append(cmd)
            return {"ok": True, "stdout": "{}"}

        with mock.patch.object(setup_tools.shutil, "which", return_value="/usr/bin/openclaw"):
            with mock.patch.object(setup_tools, "command_json_result", side_effect=fake_json_result):
                result = setup_tools.check_web_tools(True, 10)

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ["openclaw", "infer", "web", "search"])
        self.assertNotIn("fetch", result)

    def test_channel_status_uses_telegram_channel_probe(self):
        calls = []

        def fake_json_result(cmd, timeout):
            calls.append(cmd)
            return {"ok": True, "stdout": "telegram default: works"}

        with mock.patch.object(setup_tools.shutil, "which", return_value="/usr/bin/openclaw"):
            with mock.patch.object(setup_tools, "command_json_result", side_effect=fake_json_result):
                result = setup_tools.check_channel_status(True, 10)

        self.assertTrue(result["ok"])
        self.assertEqual(calls[0][:5], ["openclaw", "channels", "status", "--channel", "telegram"])
        self.assertIn("--probe", calls[0])

    def test_channel_status_fails_on_probe_failure_text(self):
        def fake_json_result(cmd, timeout):
            return {"ok": True, "stdout": "telegram default: probe failed"}

        with mock.patch.object(setup_tools.shutil, "which", return_value="/usr/bin/openclaw"):
            with mock.patch.object(setup_tools, "command_json_result", side_effect=fake_json_result):
                result = setup_tools.check_channel_status(True, 10)

        self.assertFalse(result["ok"])

    def test_audio_runtime_marks_unknown_tts_language_unsupported(self):
        result = setup_tools.check_audio_runtime(True, 10, "Klingon")

        self.assertFalse(result["google_tts"]["ok"])
        self.assertEqual(result["google_tts"]["status"], "unsupported_language")
        self.assertIsNone(result["google_tts"]["lang"])

    def test_blocked_next_action_has_no_command(self):
        status, next_action = setup_run.render_readiness_result(
            problems=["web_search_unavailable"],
            warnings=[],
            fallback_template="ready",
            context={"config_command": "python3 config_status.py", "problems": "web_search_unavailable", "warnings": ""},
        )

        self.assertEqual(
            status,
            "Setup cannot continue because web search is unavailable.",
        )
        self.assertNotIn("command", next_action)
        self.assertLessEqual(set(next_action), {"command", "instructions"})
        self.assertIn("web search is unavailable", " ".join(next_action["instructions"]))

    def test_warning_status_still_runs_config_status(self):
        status, next_action = setup_run.render_readiness_result(
            problems=[],
            warnings=["ffmpeg_missing_speed_adjustment_unavailable"],
            fallback_template="ready",
            context={"config_command": "python3 config_status.py", "problems": "", "warnings": "ffmpeg_missing_speed_adjustment_unavailable"},
        )

        self.assertEqual(
            status,
            "Setup readiness checks passed, but ffmpeg is missing and audio speed adjustment is unavailable.",
        )
        self.assertEqual(next_action["command"], "python3 config_status.py")
        self.assertLessEqual(set(next_action), {"command", "instructions"})
        self.assertIn("ffmpeg is missing", " ".join(next_action["instructions"]))

    def test_setup_log_templates_control_known_outputs(self):
        templates = setup_run.load_log_templates()
        codes = {
            "openclaw_cli_unavailable",
            "cron_cli_unavailable",
            "cron_status_unverified",
            "model_runtime_unavailable",
            "web_search_unavailable",
            "telegram_channel_status_unverified",
            "required_readiness_failed",
            "workspace_rules_missing",
            "workspace_review_required",
            "ready_with_notes",
            "gateway_secret_ref_unavailable",
            "google_tts_language_unsupported",
            "google_tts_unavailable",
            "model_fallback_status_unverified",
            "model_fallback_missing",
            "curl_missing_using_urllib_fallback",
            "ffmpeg_missing_using_binary_mp3_append_fallback",
            "ffmpeg_missing_speed_adjustment_unavailable",
            "system_ready",
            "system_ready_with_notes",
            "ready",
            "invalid_arguments",
            "setup_runner_exception",
        }

        self.assertTrue(codes.issubset(set(templates)))
        for template in templates.values():
            self.assertEqual(set(template), {"status", "next_action"})
        self.assertEqual(
            templates["cron_cli_unavailable"]["status"],
            "Setup cannot continue because OpenClaw cron commands are unavailable.",
        )

    def test_multiple_readiness_problems_are_listed_in_status(self):
        status, next_action = setup_run.render_readiness_result(
            problems=["web_search_unavailable", "model_runtime_unavailable"],
            warnings=[],
            fallback_template="ready",
            context={
                "config_command": "python3 config_status.py",
                "problems": "web_search_unavailable, model_runtime_unavailable",
                "warnings": "",
            },
        )

        self.assertEqual(
            status,
            "Setup cannot continue because required readiness checks failed: web_search_unavailable, model_runtime_unavailable.",
        )
        self.assertNotIn("command", next_action)

    def test_setup_runner_agent_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SETUP_RUN_SCRIPT),
                    "tools",
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--no-cli",
                    "--agents-reviewed",
                    "--agent",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            self.assertEqual(result.stderr, "")
            assert_agent_contract(self, data)
            self.assertEqual(data["status"], "Setup readiness checks passed and configuration status can be checked.")
            self.assertIn("config_status.py", data["next_action"]["command"])

    def test_setup_runner_invalid_args_return_json(self):
        result = subprocess.run(
            [sys.executable, str(SETUP_RUN_SCRIPT), "--not-a-real-flag"],
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(result.stdout)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        assert_agent_contract(self, data)
        self.assertIn("invalid arguments", data["status"])

    def test_setup_runner_routes_to_agents_review_before_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")
            (tmp_path / "AGENTS.md").write_text(
                "# AGENTS.md\n\n## First Run\n\nExisting setup without Morning Report details.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SETUP_RUN_SCRIPT),
                    "system",
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--agents",
                    str(tmp_path / "AGENTS.md"),
                    "--no-cli",
                    "--agent",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            self.assertEqual(result.stderr, "")
            assert_agent_contract(self, data)
            self.assertEqual(data["status"], "AGENTS.md must be reviewed before Morning Report setup continues.")
            self.assertIn("--agents-reviewed", data["next_action"]["command"])
            self.assertIn("Read AGENTS.md.", data["next_action"]["instructions"])

    def test_setup_runner_continues_after_agents_reviewed_without_content_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")
            (tmp_path / "AGENTS.md").write_text(
                "# AGENTS.md\n\n## First Run\n\nStill no Morning Report rule here.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SETUP_RUN_SCRIPT),
                    "system",
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--agents",
                    str(tmp_path / "AGENTS.md"),
                    "--no-cli",
                    "--agents-reviewed",
                    "--agent",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            assert_agent_contract(self, data)
            self.assertEqual(data["status"], "Setup system phase passed and tool readiness can be checked.")
            self.assertIn("setup/run.py tools", data["next_action"]["command"])


if __name__ == "__main__":
    unittest.main()
