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
        "fallback_provider": "exa",
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


def candidate(url: str = "https://example.com/article") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "query": "test",
        "title": "Test article",
        "url": url,
        "canonical_url": url,
        "description": "",
        "site_name": "example.com",
        "search_published_at": now,
        "search_published_source": "published",
        "host": "example.com",
    }


def firecrawl_success(text: str = "Readable fetched article text with enough characters.") -> dict:
    return {
        "ok": True,
        "engine": "firecrawl",
        "primary_engine": "firecrawl",
        "fallback_used": False,
        "status_code": 200,
        "final_url": "https://example.com/article",
        "truncated": False,
        "text": text,
    }


def firecrawl_failure(
    reason: str,
    *,
    retryable: bool = False,
    fallback_allowed: bool = True,
    disable_firecrawl_for_run: bool = False,
    status_code: int | None = None,
) -> dict:
    result = {
        "ok": False,
        "engine": "firecrawl",
        "primary_engine": "firecrawl",
        "fallback_used": False,
        "reason": reason,
        "retryable": retryable,
        "fallback_allowed": fallback_allowed,
        "disable_firecrawl_for_run": disable_firecrawl_for_run,
    }
    if status_code is not None:
        result["status_code"] = status_code
    return result


def python_success(text: str = "Readable Python fallback text with enough characters.") -> dict:
    return {
        "ok": True,
        "status_code": 200,
        "final_url": "https://example.com/article",
        "content_type": "text/html",
        "bytes_read": 100,
        "truncated": False,
        "text": text,
    }


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

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=lambda url, timeout: firecrawl_success()) as firecrawl_mock:
                    with mock.patch.object(collector, "fetch_url") as python_mock:
                        sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(args(), Path(tmp))
                        self.assertTrue(Path(sources[0]["fetch"]["text_file"]).exists())

        self.assertEqual(len(sources), 2)
        self.assertEqual(firecrawl_mock.call_count, 2)
        python_mock.assert_not_called()
        self.assertEqual(len(candidates), 2)
        self.assertEqual(search_runs[0]["new_candidate_count"], 2)
        self.assertEqual([item["reason"] for item in rejected], ["outside_freshness_window", "duplicate"])
        self.assertEqual(sources[0]["canonical_url"], "https://example.com/recent")
        self.assertEqual(sources[0]["fetch"]["engine"], "firecrawl")
        self.assertEqual(sources[0]["search_provider"], "brave")
        self.assertFalse(sources[0]["search_fallback_used"])
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

        def fake_firecrawl(url, timeout):
            if url.endswith("/1"):
                return firecrawl_failure("not_found", fallback_allowed=False, status_code=404)
            return firecrawl_success()

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=fake_firecrawl):
                    sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                        args(target_fetched=3, max_search_calls=5),
                        Path(tmp),
                    )

        self.assertEqual(len(sources), 3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(search_runs), 2)
        self.assertEqual(len(candidates), 4)
        self.assertEqual(rejected[0]["reason"], "fetch_failed")

    def test_brave_rate_limit_falls_back_to_exa_and_disables_primary_for_run(self):
        now = datetime.now(timezone.utc).isoformat()
        calls: list[tuple[str, str | None]] = []

        def fake_search(query, limit, provider, timeout):
            calls.append((query, provider))
            if provider == "brave":
                raise RuntimeError("monthly quota limit exceeded")
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {
                                    "title": f"Exa source {len(calls)}",
                                    "url": f"https://example.com/exa-{len(calls)}",
                                    "published": now,
                                }
                            ]
                        }
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=lambda url, timeout: firecrawl_success()):
                    sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                        args(target_fetched=2, max_search_calls=5),
                        Path(tmp),
                    )

        self.assertEqual(len(sources), 2)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(calls[0][1], "brave")
        self.assertEqual(calls[1][1], "exa")
        self.assertEqual(calls[2][1], "exa")
        self.assertEqual([run["provider_used"] for run in search_runs], ["exa", "exa"])
        self.assertTrue(all(run["fallback_used"] for run in search_runs))
        self.assertTrue(search_runs[0]["primary_disabled_for_run"])
        self.assertEqual(search_runs[0]["primary_search_error"]["reason"], "search_rate_limited")
        self.assertEqual(sources[0]["search_provider"], "exa")
        self.assertTrue(sources[0]["search_fallback_used"])
        self.assertEqual(sources[0]["primary_search_provider"], "brave")
        self.assertEqual(len(candidates), 2)

    def test_primary_search_success_does_not_call_fallback(self):
        now = datetime.now(timezone.utc).isoformat()
        calls: list[str | None] = []

        def fake_search(query, limit, provider, timeout):
            calls.append(provider)
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {"title": "One", "url": "https://example.com/one", "published": now},
                                {"title": "Two", "url": "https://example.com/two", "published": now},
                            ]
                        }
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=lambda url, timeout: firecrawl_success()):
                    sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                        args(target_fetched=2),
                        Path(tmp),
                    )

        self.assertEqual(len(sources), 2)
        self.assertEqual(rejected, [])
        self.assertEqual(calls, ["brave"])
        self.assertFalse(search_runs[0]["fallback_used"])
        self.assertEqual(search_runs[0]["provider_used"], "brave")

    def test_firecrawl_success_accepts_source_without_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_firecrawl_fetch", return_value=firecrawl_success()) as firecrawl_mock:
                with mock.patch.object(collector, "fetch_url") as python_mock:
                    source, rejection = collector.fetch_candidate(candidate(), args(), Path(tmp), 1, collector.new_fetch_state())

        self.assertIsNone(rejection)
        self.assertIsNotNone(source)
        self.assertEqual(source["fetch"]["engine"], "firecrawl")
        self.assertFalse(source["fetch"]["fallback_used"])
        self.assertEqual(firecrawl_mock.call_count, 1)
        python_mock.assert_not_called()

    def test_firecrawl_empty_text_retries_then_uses_python_fallback(self):
        empty = firecrawl_failure("empty_text", retryable=True, fallback_allowed=True)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=[empty, empty]) as firecrawl_mock:
                with mock.patch.object(collector, "fetch_url", return_value=python_success()) as python_mock:
                    with mock.patch.object(collector.time, "sleep"):
                        source, rejection = collector.fetch_candidate(candidate(), args(), Path(tmp), 1, collector.new_fetch_state())

        self.assertIsNone(rejection)
        self.assertEqual(source["fetch"]["engine"], "python")
        self.assertTrue(source["fetch"]["fallback_used"])
        self.assertEqual(source["fetch"]["primary_fetch_error"], "empty_text")
        self.assertEqual(firecrawl_mock.call_count, 2)
        self.assertEqual(python_mock.call_count, 1)

    def test_firecrawl_short_text_rejects_without_python_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_firecrawl_fetch", return_value=firecrawl_success("short")):
                with mock.patch.object(collector, "fetch_url") as python_mock:
                    source, rejection = collector.fetch_candidate(candidate(), args(min_text_chars=20), Path(tmp), 1, collector.new_fetch_state())

        self.assertIsNone(source)
        self.assertEqual(rejection["reason"], "fetched_text_too_short")
        self.assertEqual(rejection["fetch"]["text_char_count"], 5)
        python_mock.assert_not_called()

    def test_firecrawl_timeout_retries_then_uses_python_fallback(self):
        timeout = firecrawl_failure("firecrawl_timeout", retryable=True, fallback_allowed=True)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_firecrawl_fetch", side_effect=[timeout, timeout]) as firecrawl_mock:
                with mock.patch.object(collector, "fetch_url", return_value=python_success()) as python_mock:
                    with mock.patch.object(collector.time, "sleep"):
                        source, rejection = collector.fetch_candidate(candidate(), args(), Path(tmp), 1, collector.new_fetch_state())

        self.assertIsNone(rejection)
        self.assertEqual(source["fetch"]["engine"], "python")
        self.assertEqual(source["fetch"]["primary_fetch_error"], "firecrawl_timeout")
        self.assertEqual(firecrawl_mock.call_count, 2)
        self.assertEqual(python_mock.call_count, 1)

    def test_firecrawl_auth_failure_disables_firecrawl_for_run(self):
        now = datetime.now(timezone.utc).isoformat()

        def fake_search(query, limit, provider, timeout):
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {"title": "One", "url": "https://example.com/one", "published": now},
                                {"title": "Two", "url": "https://example.com/two", "published": now},
                            ]
                        }
                    }
                ]
            }

        auth = firecrawl_failure(
            "firecrawl_auth_unavailable",
            fallback_allowed=True,
            disable_firecrawl_for_run=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", return_value=auth) as firecrawl_mock:
                    with mock.patch.object(collector, "fetch_url", side_effect=lambda url, timeout, max_bytes: python_success()) as python_mock:
                        sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                            args(target_fetched=2),
                            Path(tmp),
                        )

        self.assertEqual(len(sources), 2)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(firecrawl_mock.call_count, 1)
        self.assertEqual(python_mock.call_count, 2)
        self.assertEqual(sources[0]["fetch"]["primary_fetch_error"], "firecrawl_auth_unavailable")
        self.assertEqual(sources[1]["fetch"]["primary_fetch_error"], "firecrawl_auth_unavailable")

    def test_three_retryable_firecrawl_failures_disable_firecrawl_for_remaining_urls(self):
        now = datetime.now(timezone.utc).isoformat()

        def fake_search(query, limit, provider, timeout):
            return {
                "outputs": [
                    {
                        "result": {
                            "results": [
                                {"title": str(index), "url": f"https://example.com/{index}", "published": now}
                                for index in range(1, 5)
                            ]
                        }
                    }
                ]
            }

        timeout = firecrawl_failure("firecrawl_timeout", retryable=True, fallback_allowed=True)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_search", side_effect=fake_search):
                with mock.patch.object(collector, "run_firecrawl_fetch", return_value=timeout) as firecrawl_mock:
                    with mock.patch.object(collector, "fetch_url", side_effect=lambda url, timeout, max_bytes: python_success()) as python_mock:
                        with mock.patch.object(collector.time, "sleep"):
                            sources, rejected, search_runs, candidates = collector.collect_sources_incrementally(
                                args(target_fetched=4),
                                Path(tmp),
                            )

        self.assertEqual(len(sources), 4)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(firecrawl_mock.call_count, 6)
        self.assertEqual(python_mock.call_count, 4)
        self.assertTrue(all(source["fetch"]["engine"] == "python" for source in sources))

    def test_firecrawl_404_rejects_without_python_fallback(self):
        not_found = firecrawl_failure("not_found", fallback_allowed=False, status_code=404)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(collector, "run_firecrawl_fetch", return_value=not_found):
                with mock.patch.object(collector, "fetch_url") as python_mock:
                    source, rejection = collector.fetch_candidate(candidate(), args(), Path(tmp), 1, collector.new_fetch_state())

        self.assertIsNone(source)
        self.assertEqual(rejection["reason"], "fetch_failed")
        self.assertEqual(rejection["fetch"]["reason"], "not_found")
        python_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
