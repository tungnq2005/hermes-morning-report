import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from report import (  # noqa: E402
    common,
    record_audio_history,
    record_report_history,
    source_collection,
    validate_report_text,
)


def write_config(state: Path, user: Path) -> None:
    state.write_text(
        "# Current Topics\n\n"
        "## Setup status\n\n"
        "Status: configured\n\n"
        "## Active topics\n\n"
        "1. Gold market\n\n"
        "## Optional topics\n\n"
        "None provided.\n\n"
        "## User priority\n\n"
        "1. Gold market\n\n"
        "## Report preferences\n\n"
        "- Delivery time: 7:00 AM\n"
        "- Timezone: Asia/Ho_Chi_Minh\n"
        "- Report style: Concise\n"
        "- Report language: English\n"
        "- Audio summary: Enabled\n"
        "- Delivery channel: Telegram\n",
        encoding="utf-8",
    )
    user.write_text("# USER\n", encoding="utf-8")


def prepare_args(tmp: Path) -> Namespace:
    return Namespace(
        work_dir=str(tmp / "run"),
        state=str(tmp / "current-topics.md"),
        user=str(tmp / "USER.md"),
        report_file=str(tmp / "morning-report.md"),
        audio_script_file=str(tmp / "morning-report-audio.txt"),
        audio_file=str(tmp / "morning-report.mp3"),
        query=None,
        provider="brave",
        fallback_provider="exa",
        target_fetched=5,
        max_search_calls=5,
        limit_per_call=10,
        freshness_hours=24,
        include_social=False,
        search_timeout=10,
        fetch_timeout=10,
        max_fetch_bytes=100_000,
        min_text_chars=20,
    )


class ReportRunnerTests(unittest.TestCase):
    def test_search_and_fetch_write_report_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            write_config(state, user)

            source_items = [
                {
                    "title": f"Fresh source {index}",
                    "canonical_url": f"https://example.com/fresh-{index}",
                    "host": "example.com",
                    "site_name": "Example",
                    "published_at": "2026-07-04T00:00:00+00:00",
                    "published_basis": "search_metadata",
                    "freshness_status": "valid_24h",
                    "fetch": {
                        "text_file": str(tmp_path / f"source-{index}.txt"),
                        "text_char_count": 1200,
                    },
                }
                for index in range(1, 6)
            ]
            candidates = [
                {
                    "title": f"Fresh source {index}",
                    "canonical_url": f"https://example.com/fresh-{index}",
                    "host": "example.com",
                    "site_name": "Example",
                    "search_published_at": "2026-07-04T00:00:00+00:00",
                    "search_published_source": "published",
                }
                for index in range(1, 6)
            ]

            search_result = source_collection.search_phase(prepare_args(tmp_path))
            with mock.patch.object(
                source_collection.web_source_collector,
                "collect_sources_incrementally",
                return_value=(source_items, [], [{"query": "Gold market"}], candidates),
            ):
                result = source_collection.fetch_phase(prepare_args(tmp_path))

            self.assertTrue(search_result["success"])
            self.assertTrue(result["success"])
            self.assertEqual(search_result["next_action"]["type"], "fetch_sources")
            self.assertEqual(search_result["search_collection"]["status"], "planned")
            self.assertIn("fetch", search_result["next_action"]["command"])
            self.assertEqual(result["next_action"]["type"], "write_report")
            self.assertIn("validate-report", result["next_action"]["next_command"])
            self.assertEqual(result["config"]["report_style"], "concise")
            self.assertEqual(result["config"]["report_language"], "English")
            self.assertEqual(result["source_collection"]["source_count"], 5)
            self.assertEqual(result["source_collection"]["fetched_sources"][0]["url"], "https://example.com/fresh-1")
            self.assertTrue((tmp_path / "run" / "run-state.json").exists())

    def test_validate_report_phase_uses_runner_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "run"
            report = tmp_path / "morning-report.md"
            report.write_text(
                "# Morning Brief — Test\n\n"
                "## Snapshot\n"
                "- One important update.\n\n"
                "## Key updates\n"
                "- Update one with [evidence](https://example.com/1).\n"
                "- Update two with [evidence](https://example.com/2).\n"
                "- Update three with [evidence](https://example.com/3).\n\n"
                "## Watch next\n"
                "- Signal one.\n",
                encoding="utf-8",
            )
            common.save_run_state(
                work_dir,
                {
                    "success": True,
                    "phase": "fetch",
                    "work_dir": str(work_dir),
                    "report_file": str(report),
                    "audio_script_file": str(tmp_path / "audio.txt"),
                    "audio_file": str(tmp_path / "audio.mp3"),
                    "config": {
                        "report_style": "concise",
                        "report_language": "English",
                        "audio_enabled": False,
                    },
                    "audio": {"enabled": False, "status": "disabled"},
                },
            )

            result = validate_report_text.validate_report_phase(Namespace(work_dir=str(work_dir), report_file=None))

            self.assertTrue(result["success"])
            self.assertEqual(result["next_action"]["type"], "send_report")
            self.assertIn("record-report", result["next_action"]["next_command"])

    def test_validate_report_rejects_unfetched_evidence_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "run"
            report = tmp_path / "morning-report.md"
            source_manifest = tmp_path / "source-manifest.json"
            fetched_url = "https://example.com/fetched"
            report.write_text(
                "# Morning Brief — Test\n\n"
                "## Snapshot\n"
                "- One important update.\n\n"
                "## Key updates\n"
                f"- Valid update with [evidence]({fetched_url}).\n"
                "- Invalid update with [evidence](https://example.com/inner-article).\n"
                "- Update three.\n\n"
                "## Watch next\n"
                "- Signal one.\n",
                encoding="utf-8",
            )
            source_manifest.write_text(
                json.dumps(
                    {
                        "source_count": 1,
                        "fresh_24h_count": 1,
                        "fetched_sources": [{"url": fetched_url}],
                    }
                ),
                encoding="utf-8",
            )
            common.save_run_state(
                work_dir,
                {
                    "success": True,
                    "phase": "fetch",
                    "work_dir": str(work_dir),
                    "report_file": str(report),
                    "audio_script_file": str(tmp_path / "audio.txt"),
                    "audio_file": str(tmp_path / "audio.mp3"),
                    "config": {
                        "report_style": "concise",
                        "report_language": "English",
                        "audio_enabled": False,
                    },
                    "source_collection": {"manifest_path": str(source_manifest)},
                    "audio": {"enabled": False, "status": "disabled"},
                },
            )

            result = validate_report_text.validate_report_phase(Namespace(work_dir=str(work_dir), report_file=None))

            self.assertFalse(result["success"])
            codes = {issue["code"] for issue in result["validation"]["report"]["issues"]}
            self.assertIn("unfetched_evidence_link", codes)
            self.assertEqual(result["next_action"]["type"], "revise_report")

    def test_validate_report_rejects_decorative_title_symbol(self):
        report = (
            "# ⚡ Morning Brief — Test\n\n"
            "## Snapshot\n"
            "- One important update.\n\n"
            "## Key updates\n"
            "- Update one with [evidence](https://example.com/1).\n"
            "- Update two with [evidence](https://example.com/2).\n"
            "- Update three with [evidence](https://example.com/3).\n\n"
            "## Watch next\n"
            "- Signal one.\n"
        )

        result = validate_report_text.validate_report(report, "concise")

        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("decorative_symbol_in_title", codes)

    def test_failed_report_validation_has_no_send_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "run"
            report = tmp_path / "morning-report.md"
            report.write_text("# Too Short\n", encoding="utf-8")
            common.save_run_state(
                work_dir,
                {
                    "success": True,
                    "phase": "fetch",
                    "work_dir": str(work_dir),
                    "report_file": str(report),
                    "audio_script_file": str(tmp_path / "audio.txt"),
                    "audio_file": str(tmp_path / "audio.mp3"),
                    "config": {
                        "report_style": "concise",
                        "report_language": "English",
                        "audio_enabled": True,
                    },
                    "audio": {"enabled": True, "status": "pending"},
                },
            )

            result = validate_report_text.validate_report_phase(Namespace(work_dir=str(work_dir), report_file=None))

            self.assertFalse(result["success"])
            self.assertEqual(result["next_action"]["type"], "revise_report")
            self.assertNotIn("after_send", result["next_action"])
            self.assertIn("validate-report", result["next_action"]["next_command"])

    def test_fetch_without_readable_sources_stops_without_report_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            write_config(state, user)
            source_collection.search_phase(prepare_args(tmp_path))
            with mock.patch.object(
                source_collection.web_source_collector,
                "collect_sources_incrementally",
                return_value=([], [], [], []),
            ):
                result = source_collection.fetch_phase(prepare_args(tmp_path))

            self.assertFalse(result["success"])
            self.assertEqual(result["next_action"]["type"], "stop")
            self.assertEqual(result["next_action"]["reason"], "not_enough_24h_sources")
            self.assertNotIn("instructions", result["next_action"])
            self.assertNotIn("after_write", result["next_action"])

    def test_record_report_runs_after_text_send_and_points_to_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            state_file = tmp_path / "current-topics.md"
            user = tmp_path / "USER.md"
            audit = tmp_path / "audit.log"
            history = tmp_path / "history"
            work_dir = tmp_path / "run"
            report = tmp_path / "morning-report.md"
            source_manifest = tmp_path / "source-manifest.json"
            write_config(state_file, user)
            report.write_text(
                "# Morning Brief — Test\n\n"
                "## Snapshot\n- One update.\n\n"
                "## Key updates\n"
                "- Update with [evidence](https://example.com/1).\n"
                "- Update two.\n- Update three.\n\n"
                "## Watch next\n- Signal.\n",
                encoding="utf-8",
            )
            source_manifest.write_text(
                json.dumps({"failed_fetch_urls": [], "source_count": 1, "fresh_24h_count": 1}),
                encoding="utf-8",
            )
            common.save_run_state(
                work_dir,
                {
                    "success": True,
                    "phase": "validate-report",
                    "work_dir": str(work_dir),
                    "report_file": str(report),
                    "audio_script_file": str(tmp_path / "audio.txt"),
                    "audio_file": str(tmp_path / "audio.mp3"),
                    "config": {
                        "report_style": "concise",
                        "report_language": "English",
                        "audio_enabled": True,
                    },
                    "source_collection": {"manifest_path": str(source_manifest)},
                    "audio": {"enabled": True, "status": "pending"},
                },
            )

            result = record_report_history.record_report_phase(
                Namespace(
                    work_dir=str(work_dir),
                    report_file=None,
                    state=str(state_file),
                    user=str(user),
                    history_dir=str(history),
                    audit_log=str(audit),
                    send_status="sent",
                    audio_status=None,
                )
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["phase"], "record-report")
            self.assertEqual(result["next_action"]["type"], "write_audio_script")
            self.assertTrue(Path(result["history"]["run_dir"]).exists())
            manifest = json.loads(Path(result["history"]["manifest_path"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["audio"]["status"], "pending")
            self.assertEqual(manifest["source_collection"]["source_count"], 1)
            state_after = common.load_run_state(work_dir)
            self.assertEqual(state_after["phase"], "record-report")
            self.assertTrue(state_after["can_continue"])
            self.assertTrue(audit.exists())

    def test_record_audio_updates_unified_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "run"
            audio_file = tmp_path / "morning-report.mp3"
            audio_script = tmp_path / "audio.txt"
            history = tmp_path / "history"
            run_dir = history / "2026-07-07" / "120000-test"
            manifest_path = run_dir / "manifest.json"
            audit = tmp_path / "audit.log"
            run_dir.mkdir(parents=True)
            audio_file.write_bytes(b"mp3-data" * 100)
            audio_script.write_text("audio script", encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "success": True,
                        "created_at": "2026-07-07T12:00:00+00:00",
                        "updated_at": "2026-07-07T12:00:00+00:00",
                        "run_id": "120000-test",
                        "run_dir": str(run_dir),
                        "topics": ["World Cup 2026"],
                        "report": {"status": "sent", "file": str(run_dir / "report.md")},
                        "audio": {"status": "pending"},
                        "delivery": {"channel": "Telegram", "report_send_status": "sent", "audio_send_status": None},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            common.save_run_state(
                work_dir,
                {
                    "success": True,
                    "phase": "generate-audio",
                    "work_dir": str(work_dir),
                    "config": {
                        "report_language": "English",
                        "audio_enabled": True,
                    },
                    "audio": {
                        "status": "generated",
                        "file": str(audio_file),
                        "script_file": str(audio_script),
                    },
                    "history": {"run_dir": str(run_dir), "manifest_path": str(manifest_path)},
                },
            )

            result = record_audio_history.record_audio_phase(
                Namespace(
                    work_dir=str(work_dir),
                    audio_file=None,
                    audio_script_file=None,
                    audio_manifest=None,
                    history_dir=str(history),
                    audit_log=str(audit),
                    audio_status="sent",
                    send_status="sent",
                )
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["phase"], "record-audio")
            self.assertEqual(result["audio_history"]["audio"]["status"], "sent")
            self.assertEqual(result["audio_history"]["delivery"]["audio_send_status"], "sent")
            self.assertTrue((run_dir / "morning-report.mp3").exists())
            self.assertTrue((run_dir / "audio-script.txt").exists())
            state_after = common.load_run_state(work_dir)
            self.assertEqual(state_after["phase"], "complete")
            self.assertFalse(state_after["can_continue"])
            self.assertTrue(audit.exists())

    def test_record_audio_failure_updates_existing_history_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "run"
            history = tmp_path / "history"
            run_dir = history / "2026-07-07" / "120000-test"
            manifest_path = run_dir / "manifest.json"
            audit = tmp_path / "audit.log"
            run_dir.mkdir(parents=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "success": True,
                        "created_at": "2026-07-07T12:00:00+00:00",
                        "updated_at": "2026-07-07T12:00:00+00:00",
                        "run_id": "120000-test",
                        "run_dir": str(run_dir),
                        "topics": ["World Cup 2026"],
                        "report": {"status": "sent", "file": str(run_dir / "report.md")},
                        "audio": {"status": "pending"},
                        "delivery": {"channel": "Telegram", "report_send_status": "sent", "audio_send_status": None},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            common.save_run_state(
                work_dir,
                {
                    "success": False,
                    "phase": "generate-audio",
                    "work_dir": str(work_dir),
                    "config": {
                        "report_language": "English",
                        "audio_enabled": True,
                    },
                    "audio": {
                        "status": "failed",
                        "error": "tts failed",
                    },
                    "history": {"run_dir": str(run_dir), "manifest_path": str(manifest_path)},
                },
            )

            result = record_audio_history.record_audio_phase(
                Namespace(
                    work_dir=str(work_dir),
                    audio_file=None,
                    audio_script_file=None,
                    audio_manifest=None,
                    history_dir=str(history),
                    audit_log=str(audit),
                    audio_status="failed",
                    send_status="failure_notice_sent",
                )
            )

            self.assertTrue(result["success"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["report"]["status"], "sent")
            self.assertEqual(manifest["audio"]["status"], "failed")
            self.assertEqual(manifest["audio"]["error"], "tts failed")
            self.assertEqual(manifest["delivery"]["audio_send_status"], "failure_notice_sent")


if __name__ == "__main__":
    unittest.main()
