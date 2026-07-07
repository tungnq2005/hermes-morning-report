import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


import sys

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from report import web_source_collector as collector  # noqa: E402


def args(**overrides):
    base = {
        "topic": "Gold market",
        "query": None,
        "provider": "brave",
        "target_fetched": 2,
        "max_search_calls": 1,
        "limit_per_call": 10,
        "search_timeout": 10,
        "fetch_timeout": 10,
        "max_fetch_bytes": 100_000,
        "min_text_chars": 20,
        "include_social": False,
        "freshness_hours": 24,
    }
    base.update(overrides)
    return Namespace(**base)


class WebSourceCollectorTests(unittest.TestCase):
    def test_incremental_collection_fetches_only_deduped_24h_urls(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=2)).isoformat()
        old = (now - timedelta(days=3)).isoformat()

        def fake_search(query, limit, provider, timeout):
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {"title": "Recent", "url": "https://example.com/recent?utm_source=x", "published": recent},
                                {"title": "Old", "url": "https://example.com/old", "published": old},
                                {"title": "Recent duplicate", "url": "https://example.com/recent?utm_source=y", "published": recent},
                                {"title": "Second recent", "url": "https://example.com/second", "published": recent},
                            ]
                        }
                    }
                ]
            }

        def fake_fetch(url, timeout, max_bytes):
            return {
                "ok": True,
                "status_code": 200,
                "final_url": url,
                "content_type": "text/html",
                "bytes_read": 100,
                "truncated": False,
                "text": "Readable fetched article text with enough characters.",
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "fetch_url", side_effect=fake_fetch) as fetch_mock:
                    sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(args(), Path(tmp))
                    self.assertTrue(Path(sources[0]["fetch"]["text_file"]).exists())

        self.assertEqual(len(sources), 2)
        self.assertEqual(fetch_mock.call_count, 2)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(search_runs[0]["new_candidate_count"], 2)
        self.assertEqual([item["reason"] for item in rejected], ["outside_freshness_window", "duplicate"])
        self.assertEqual(sources[0]["canonical_url"], "https://example.com/recent")
        self.assertEqual(sources[0]["freshness_status"], "valid_24h")
        self.assertEqual(sources[1]["canonical_url"], "https://example.com/second")
        self.assertEqual(sources[1]["freshness_status"], "valid_24h")

    def test_incremental_collection_searches_again_until_target_then_stops(self):
        now = datetime.now(timezone.utc).isoformat()
        calls: list[str] = []

        def fake_search(query, limit, provider, timeout):
            calls.append(query)
            suffix = len(calls)
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {"title": f"Source {suffix}", "url": f"https://example.com/{suffix}", "published": now},
                                {"title": f"Extra {suffix}", "url": f"https://example.com/extra-{suffix}", "published": now},
                            ]
                        }
                    }
                ]
            }

        def fake_fetch(url, timeout, max_bytes):
            if url.endswith("/1"):
                return {"ok": False, "error": "blocked"}
            return {
                "ok": True,
                "status_code": 200,
                "final_url": url,
                "content_type": "text/html",
                "bytes_read": 100,
                "truncated": False,
                "text": "Readable fetched article text with enough characters.",
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "fetch_url", side_effect=fake_fetch):
                    sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                        args(target_fetched=3, max_search_calls=5),
                        Path(tmp),
                    )

        self.assertEqual(len(sources), 3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(search_runs), 2)
        self.assertEqual(len(candidates), 4)
        self.assertEqual(rejected[0]["reason"], "fetch_failed")


if __name__ == "__main__":
    unittest.main()
