import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = SKILL_DIR / "scripts" / "update_config.py"
STATUS_SCRIPT = SKILL_DIR / "scripts" / "config_status.py"


def run_update_result(tmp_path: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(UPDATE_SCRIPT),
            "--state",
            str(tmp_path / "current-topics.md"),
            "--user",
            str(tmp_path / "USER.md"),
            "--audit-log",
            str(tmp_path / "audit.log"),
            *args,
        ],
        capture_output=True,
        text=True,
        check=check,
    )


def run_update(tmp_path: Path, *args: str) -> dict:
    result = run_update_result(tmp_path, *args, check=True)
    return json.loads(result.stdout)


def setup_config(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text("# USER\n\nExisting user notes.\n", encoding="utf-8")
    run_update(
        tmp_path,
        "setup",
        "--topic",
        "AI agents",
        "--topic",
        "Vietnam real estate",
        "--optional-topic",
        "Macro watchlist",
        "--delivery-time",
        "7:00 AM",
        "--timezone",
        "Asia/Ho_Chi_Minh",
        "--report-style",
        "Concise",
        "--report-language",
        "English",
        "--audio-summary",
        "Disabled",
        "--delivery-channel",
        "Telegram",
        "--user-status",
        "enabled",
    )


def audit_records(tmp_path: Path) -> list[dict]:
    audit = tmp_path / "audit.log"
    return [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]


class UpdateConfigEdgeTests(unittest.TestCase):
    def test_add_topic_dedupes_case_insensitively_and_syncs_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)

            data = run_update(
                tmp_path,
                "add-topic",
                "--topic",
                "ai agents",
                "--topic",
                "Crypto",
                "--sync-user",
            )

            self.assertEqual(data["state"]["active_topics"], ["AI agents", "Vietnam real estate", "Crypto"])
            self.assertEqual(data["state"]["preferences"]["Report style"], "concise")
            user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
            self.assertIn("- Topics: AI agents, Vietnam real estate, Crypto", user_text)
            self.assertEqual(audit_records(tmp_path)[-1]["details"]["active_topics"], data["state"]["active_topics"])

    def test_remove_missing_topic_warns_without_changing_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)
            before_state = (tmp_path / "current-topics.md").read_text(encoding="utf-8")

            data = run_update(
                tmp_path,
                "remove-topic",
                "--topic",
                "No such topic",
                "--sync-user",
            )

            self.assertEqual(data["warnings"], ["topics_not_found: No such topic"])
            self.assertEqual(data["state"]["active_topics"], ["AI agents", "Vietnam real estate"])
            self.assertEqual((tmp_path / "current-topics.md").read_text(encoding="utf-8"), before_state)
            self.assertEqual(audit_records(tmp_path)[-1]["details"]["warnings"], data["warnings"])

    def test_reprioritize_unknown_topic_warns_and_keeps_unknown_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)

            data = run_update(
                tmp_path,
                "reprioritize",
                "--topic",
                "Vietnam real estate",
                "--topic",
                "Unknown topic",
                "--sync-user",
            )

            self.assertEqual(data["warnings"], ["priority_topics_not_active: Unknown topic"])
            self.assertEqual(data["state"]["active_topics"], ["AI agents", "Vietnam real estate"])
            self.assertEqual(data["state"]["user_priority"], ["Vietnam real estate", "AI agents"])

    def test_replace_topics_preserves_optional_topics_unless_explicitly_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)

            data = run_update(
                tmp_path,
                "replace-topics",
                "--topic",
                "Crypto market",
                "--sync-user",
            )

            self.assertEqual(data["state"]["active_topics"], ["Crypto market"])
            self.assertEqual(data["state"]["optional_topics"], ["Macro watchlist"])
            self.assertEqual(data["state"]["user_priority"], ["Crypto market"])

    def test_dry_run_does_not_write_state_user_or_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)
            before_state = (tmp_path / "current-topics.md").read_text(encoding="utf-8")
            before_user = (tmp_path / "USER.md").read_text(encoding="utf-8")
            before_audit = (tmp_path / "audit.log").read_text(encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(UPDATE_SCRIPT),
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--audit-log",
                    str(tmp_path / "audit.log"),
                    "--dry-run",
                    "add-topic",
                    "--topic",
                    "Crypto",
                    "--sync-user",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)

            self.assertIn("Crypto", data["state"]["active_topics"])
            self.assertEqual((tmp_path / "current-topics.md").read_text(encoding="utf-8"), before_state)
            self.assertEqual((tmp_path / "USER.md").read_text(encoding="utf-8"), before_user)
            self.assertEqual((tmp_path / "audit.log").read_text(encoding="utf-8"), before_audit)

    def test_remove_last_active_topic_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)
            run_update(
                tmp_path,
                "replace-topics",
                "--topic",
                "AI agents",
                "--sync-user",
            )
            before_state = (tmp_path / "current-topics.md").read_text(encoding="utf-8")
            before_user = (tmp_path / "USER.md").read_text(encoding="utf-8")
            before_audit = (tmp_path / "audit.log").read_text(encoding="utf-8")

            result = run_update_result(
                tmp_path,
                "remove-topic",
                "--topic",
                "AI agents",
                "--sync-user",
            )
            error = json.loads(result.stderr)

            self.assertEqual(result.returncode, 2)
            self.assertIn("cannot_remove_last_active_topic", error["error"])
            self.assertEqual((tmp_path / "current-topics.md").read_text(encoding="utf-8"), before_state)
            self.assertEqual((tmp_path / "USER.md").read_text(encoding="utf-8"), before_user)
            self.assertEqual((tmp_path / "audit.log").read_text(encoding="utf-8"), before_audit)

    def test_blank_topic_argument_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)
            before_state = (tmp_path / "current-topics.md").read_text(encoding="utf-8")
            before_user = (tmp_path / "USER.md").read_text(encoding="utf-8")
            before_audit = (tmp_path / "audit.log").read_text(encoding="utf-8")

            result = run_update_result(
                tmp_path,
                "replace-topics",
                "--topic",
                "   ",
                "--sync-user",
            )
            error = json.loads(result.stderr)

            self.assertEqual(result.returncode, 2)
            self.assertIn("topic_required", error["error"])
            self.assertEqual((tmp_path / "current-topics.md").read_text(encoding="utf-8"), before_state)
            self.assertEqual((tmp_path / "USER.md").read_text(encoding="utf-8"), before_user)
            self.assertEqual((tmp_path / "audit.log").read_text(encoding="utf-8"), before_audit)

    def test_set_status_disabled_preserves_config_and_syncs_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)

            data = run_update(
                tmp_path,
                "set-status",
                "--status",
                "disabled",
                "--sync-user",
            )

            self.assertEqual(data["state"]["status"], "disabled")
            self.assertEqual(data["state"]["active_topics"], ["AI agents", "Vietnam real estate"])
            user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
            self.assertIn("- Status: disabled", user_text)
            self.assertIn("- Topics: AI agents, Vietnam real estate", user_text)
            self.assertEqual(audit_records(tmp_path)[-1]["details"]["user_status"], "disabled")

            status = subprocess.run(
                [
                    sys.executable,
                    str(STATUS_SCRIPT),
                    "--state",
                    str(tmp_path / "current-topics.md"),
                    "--user",
                    str(tmp_path / "USER.md"),
                    "--check",
                    "--compact",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            status_data = json.loads(status.stdout)
            self.assertNotEqual(status.returncode, 0)
            self.assertFalse(status_data["configured"])
            self.assertEqual(status_data["state"]["setup_status"], "disabled")
            self.assertIn("Status: configured", status_data["missing_required"])

    def test_set_status_configured_resumes_when_config_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            setup_config(tmp_path)
            run_update(tmp_path, "set-status", "--status", "paused", "--sync-user")

            data = run_update(
                tmp_path,
                "set-status",
                "--status",
                "configured",
                "--sync-user",
            )

            self.assertEqual(data["state"]["status"], "configured")
            user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
            self.assertIn("- Status: enabled", user_text)

    def test_set_status_configured_rejects_incomplete_config_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            audit = tmp_path / "audit.log"
            state.write_text(
                "# Current Topics\n\n"
                "## Setup status\n\n"
                "Status: paused\n\n"
                "## Active topics\n\n"
                "1. AI agents\n\n"
                "## Optional topics\n\n"
                "None provided.\n\n"
                "## User priority\n\n"
                "1. AI agents\n\n"
                "## Report preferences\n\n"
                "- Delivery time: 7:00 AM\n",
                encoding="utf-8",
            )
            user.write_text("# USER\n", encoding="utf-8")
            before_state = state.read_text(encoding="utf-8")
            before_user = user.read_text(encoding="utf-8")

            result = run_update_result(
                tmp_path,
                "set-status",
                "--status",
                "configured",
                "--sync-user",
            )
            error = json.loads(result.stderr)

            self.assertEqual(result.returncode, 2)
            self.assertIn("missing_report_preferences", error["error"])
            self.assertEqual(state.read_text(encoding="utf-8"), before_state)
            self.assertEqual(user.read_text(encoding="utf-8"), before_user)
            self.assertFalse(audit.exists())

    def test_setup_normalizes_supported_report_style_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "USER.md").write_text("# USER\n", encoding="utf-8")

            data = run_update(
                tmp_path,
                "setup",
                "--topic",
                "AI agents",
                "--delivery-time",
                "7:00 AM",
                "--timezone",
                "Asia/Ho_Chi_Minh",
                "--report-style",
                "brief",
                "--report-language",
                "English",
                "--audio-summary",
                "Disabled",
                "--delivery-channel",
                "Telegram",
                "--user-status",
                "enabled",
            )

            self.assertEqual(data["state"]["preferences"]["Report style"], "concise")
            user_text = (tmp_path / "USER.md").read_text(encoding="utf-8")
            self.assertIn("- Report style: concise", user_text)

    def test_setup_rejects_unsupported_report_style_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            user = tmp_path / "USER.md"
            user.write_text("# USER\n", encoding="utf-8")

            result = run_update_result(
                tmp_path,
                "setup",
                "--topic",
                "AI agents",
                "--delivery-time",
                "7:00 AM",
                "--timezone",
                "Asia/Ho_Chi_Minh",
                "--report-style",
                "story mode",
                "--report-language",
                "English",
                "--audio-summary",
                "Disabled",
                "--delivery-channel",
                "Telegram",
                "--user-status",
                "enabled",
            )
            error = json.loads(result.stderr)

            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported_report_style", error["error"])
            self.assertFalse((tmp_path / "current-topics.md").exists())
            self.assertEqual(user.read_text(encoding="utf-8"), "# USER\n")
            self.assertFalse((tmp_path / "audit.log").exists())


if __name__ == "__main__":
    unittest.main()
