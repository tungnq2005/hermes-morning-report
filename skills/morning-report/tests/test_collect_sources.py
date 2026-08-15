"""Tests for collect_sources.py — URL normalization and filtering."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from collect_sources import (
    canonical_url, hostname, is_viable_url, write_source_text,
    collect_sources, render_collect_output, run_search_chain,
    BLOCKED_EXTENSIONS,
)

PASS = FAIL = 0


def check(desc, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        print(f"FAIL {desc}: {e}")
        FAIL += 1


# ── canonical_url ──
def test_canonical_strips_www():
    assert canonical_url("https://www.example.com/foo") == "https://example.com/foo"

def test_canonical_strips_utm():
    assert "utm_source" not in canonical_url("https://example.com?a=1&utm_source=x")

def test_canonical_strips_fbclid():
    assert "fbclid" not in canonical_url("https://example.com?a=1&fbclid=y")

def test_canonical_trailing_slash():
    assert canonical_url("https://example.com/foo/") == "https://example.com/foo"


# ── hostname ──
def test_hostname():
    assert hostname("https://www.Reuters.com/path") == "reuters.com"


# ── is_viable_url ──
def test_viable_ok():
    v, r = is_viable_url("https://reuters.com/article")
    assert v, f"expected viable, got {r}"

def test_block_social():
    v, r = is_viable_url("https://facebook.com/post")
    assert not v

def test_block_mp3():
    v, r = is_viable_url("https://example.com/song.mp3")
    assert not v, f"expected blocked for .mp3, got {v}/{r}"


# ── source text output ──
def test_write_source_text_contract():
    with tempfile.TemporaryDirectory() as tmp:
        path = write_source_text(
            Path(tmp),
            1,
            "Title\nwith spaces",
            "https://example.com/article",
            "Fetched body",
        )
        written = path.read_text(encoding="utf-8")
        assert path.parent.name == "sources"
        assert written.startswith(
            "SOURCE_TITLE: Title with spaces\n"
            "SOURCE_URL: https://example.com/article\n\n"
            "--- CONTENT ---\n\n"
        )
        assert written.endswith("Fetched body\n")


def test_multiple_topics_output_template():
    result = render_collect_output("multiple_topics")
    assert result["success"] is False
    assert "once per topic" in result["next_action"]
    assert result["topics"] == []


def test_topic_not_configured_output_template():
    result = render_collect_output("topic_not_configured")
    assert result["success"] is False
    assert "not in the configured topics" in result["next_action"]


# ── Run ──
def test_run_search_chain_uses_first_nonempty():
    def exa_ok(topic, limit, timeout):
        return [{"title": "exa1", "url": "https://exa.com/1"}]
    def brave_ok(topic, limit, timeout):
        return [{"title": "brave1", "url": "https://brave.com/1"}]
    items, engine, provider_responded = run_search_chain("t", 10, 30, (exa_ok, brave_ok))
    assert items == [{"title": "exa1", "url": "https://exa.com/1"}]
    assert engine == "exa_ok"
    assert provider_responded is True


def test_run_search_chain_falls_back_when_first_raises():
    def exa_down(topic, limit, timeout):
        raise RuntimeError("exa down")
    def brave_ok(topic, limit, timeout):
        return [{"title": "brave1", "url": "https://brave.com/1"}]
    items, engine, provider_responded = run_search_chain("t", 10, 30, (exa_down, brave_ok))
    assert items == [{"title": "brave1", "url": "https://brave.com/1"}]
    assert engine == "brave_ok"
    assert provider_responded is True


def test_run_search_chain_skips_empty_result_and_falls_back():
    def exa_empty(topic, limit, timeout):
        return []
    def brave_ok(topic, limit, timeout):
        return [{"title": "brave1", "url": "https://brave.com/1"}]
    items, engine, provider_responded = run_search_chain("t", 10, 30, (exa_empty, brave_ok))
    assert engine == "brave_ok"
    assert provider_responded is True


def test_run_search_chain_all_empty_marks_provider_responded():
    def exa_empty(topic, limit, timeout):
        return []
    def brave_empty(topic, limit, timeout):
        return []
    items, engine, provider_responded = run_search_chain("t", 10, 30, (exa_empty, brave_empty))
    assert items == []
    assert engine == ""
    assert provider_responded is True


def test_run_search_chain_all_fail_returns_empty():
    def exa_down(topic, limit, timeout):
        raise RuntimeError("exa down")
    def brave_down(topic, limit, timeout):
        raise RuntimeError("brave down")
    items, engine, provider_responded = run_search_chain("t", 10, 30, (exa_down, brave_down))
    assert items == []
    assert engine == ""
    assert provider_responded is False


def test_run_search_chain_no_searchers():
    items, engine, provider_responded = run_search_chain("t", 10, 30, ())
    assert items == []
    assert engine == ""
    assert provider_responded is False


def test_collect_sources_empty_provider_result_is_no_usable_sources():
    def exa_empty(topic, limit, timeout):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        result = collect_sources("t", run_dir=Path(tmp), searchers=(exa_empty,))
    assert result["success"] is False
    assert "not enough usable fresh sources" in result["next_action"]


def test_collect_sources_all_providers_error_is_search_provider_failed():
    def exa_down(topic, limit, timeout):
        raise RuntimeError("exa down")
    with tempfile.TemporaryDirectory() as tmp:
        result = collect_sources("t", run_dir=Path(tmp), searchers=(exa_down,))
    assert result["success"] is False
    assert "search provider failed" in result["next_action"]


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
