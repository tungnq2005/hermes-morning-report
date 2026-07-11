"""Tests for collect_sources.py — URL normalization and filtering."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from collect_sources import (
    canonical_url, hostname, is_viable_url, write_source_text,
    render_collect_output,
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
for name, fn in list(globals().items()):
    if name.startswith("test_"):
        check(name, fn)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(0 if FAIL == 0 else 1)
