#!/usr/bin/env python3
"""Collect Morning Report sources via direct search/fetch APIs.

The agent runs this helper, receives a small JSON payload with the run
directory and next action, then reads source text files from that run directory.

Search uses Exa first and falls back to Brave. Fetching uses Firecrawl first
and falls back to Python urllib.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from helpers.check_topic_config import check_topic_config


# Paths and runtime defaults
# Use .absolute() (not .resolve()) so the ~/.hermes invocation path is preserved.
# .resolve() follows the symlink to the repo path (openclaw-morning_report/...), which breaks MEDIA delivery.
SCRIPT_DIR = Path(__file__).absolute().parent
SKILL_DIR = SCRIPT_DIR.parent
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
CONFIG_PATH = SKILL_DIR / "state" / "topic-config.json"
HISTORY_DIR = SKILL_DIR / "state" / "history"
OUTPUT_TEMPLATES_PATH = SKILL_DIR / "references" / "workflow-output-templates.json"


# API endpoints
EXA_API_URL = "https://api.exa.ai/search"
BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_FRESHNESS = "pd"  # past day, matches Exa's 24h window
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


# URL and content filters
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
BLOCKED_EXTENSIONS = {
    ".avi",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mp3",
    ".mp4",
    ".png",
    ".ppt",
    ".pptx",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}
LOGIN_HOST_MARKERS = {"accounts.google.com", "login.", "signin."}
SOCIAL_HOSTS = {
    "facebook.com",
    "m.facebook.com",
    "mbasic.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "x.com",
    "twitter.com",
}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


# Env loading
def _load_env() -> None:
    env_file = HERMES_HOME / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()


# Search clients
def search_via_exa(query: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    """Search via Exa API directly."""
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        raise RuntimeError("EXA_API_KEY not set")

    payload = json.dumps(
        {
            "query": query,
            "numResults": limit,
            "type": "fast",
            "useAutoprompt": True,
            "contents": {"text": False},
            "startPublishedDate": (
                datetime.now(timezone.utc) - timedelta(hours=24)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
    ).encode()
    request = urllib.request.Request(
        EXA_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError(f"Exa search failed: {exc}") from exc

    results = data.get("results", [])
    if not isinstance(results, list):
        raise RuntimeError("Exa returned invalid results")
    return [result for result in results if isinstance(result, dict)]


def search_via_brave(query: str, limit: int, timeout: int) -> list[dict[str, Any]]:
    """Search via Brave Search API directly. Returns Exa-like items: [{"title", "url"}]."""
    api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY not set")

    params = urllib.parse.urlencode({"q": query, "count": limit, "freshness": BRAVE_FRESHNESS})
    request = urllib.request.Request(
        f"{BRAVE_API_URL}?{params}",
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError(f"Brave search failed: {exc}") from exc

    results = (data.get("web") or {}).get("results", [])
    if not isinstance(results, list):
        raise RuntimeError("Brave returned invalid results")
    items: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = str(result.get("url", "")).strip()
        if url:
            items.append({"title": str(result.get("title", "")), "url": url})
    return items


def run_search_chain(
    topic: str,
    limit: int,
    timeout: int,
    searchers: tuple,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Try each searcher in order; return items, engine name, and whether any provider responded."""
    provider_responded = False
    for searcher in searchers:
        try:
            got = searcher(topic, limit, timeout)
        except Exception:
            continue
        provider_responded = True
        if got:
            return got, getattr(searcher, "__name__", "") or "searcher", provider_responded
    return [], "", provider_responded


# URL helpers
def canonical_url(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = urllib.parse.urlencode(
        [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMS
        ],
        doseq=True,
    )
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


def hostname(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def is_viable_url(url: str) -> tuple[bool, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_scheme"
    host = parsed.netloc.lower()
    if not host:
        return False, "missing_host"
    if any(marker in host for marker in LOGIN_HOST_MARKERS):
        return False, "login_host"
    if any(host == social or host.endswith(f".{social}") for social in SOCIAL_HOSTS):
        return False, "social_skipped"
    suffix = Path(parsed.path).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        return False, f"blocked_extension:{suffix}"
    return True, "ok"


# Text extraction and fetch clients
class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag.lower() in {"p", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag.lower() in {"p", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        clean = data.strip()
        if clean:
            self.parts.append(clean)

    def text(self) -> str:
        text = html.unescape(" ".join(self.parts))
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def fetch_via_firecrawl(url: str, timeout: int) -> dict[str, Any]:
    """Fetch page content via Firecrawl API directly. Returns clean markdown."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        return {"ok": False, "reason": "no_firecrawl_key", "retryable": False}

    payload = json.dumps({"url": url, "formats": ["markdown"]}).encode()
    request = urllib.request.Request(
        FIRECRAWL_API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except Exception as exc:
        return {
            "ok": False,
            "reason": "firecrawl_error",
            "error": str(exc)[:200],
            "retryable": True,
        }
    if not data.get("success"):
        return {
            "ok": False,
            "reason": "firecrawl_failed",
            "error": str(data.get("error", ""))[:200],
            "retryable": True,
        }

    markdown = (data.get("data", {}) or {}).get("markdown", "")
    if not markdown:
        return {"ok": False, "reason": "empty_text", "retryable": True}
    return {
        "ok": True,
        "engine": "firecrawl",
        "final_url": url,
        "title": "",
        "truncated": False,
        "text": str(markdown),
    }


def fetch_url_python(url: str, timeout: int, max_bytes: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            truncated = len(data) > max_bytes
            if truncated:
                data = data[:max_bytes]
            content_type = response.headers.get("content-type", "")
            charset_match = re.search(r"charset=([^;\s]+)", content_type, re.I)
            raw = data.decode(charset_match.group(1) if charset_match else "utf-8", errors="replace")
            if "html" in content_type.lower() or "<html" in raw[:500].lower():
                extractor = TextExtractor()
                extractor.feed(raw)
                text = extractor.text()
            else:
                text = raw.strip()
            return {
                "ok": True,
                "engine": "python_urllib",
                "status_code": getattr(response, "status", None),
                "final_url": response.geturl(),
                "truncated": truncated,
                "text": text,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"http_{exc.code}", "status_code": exc.code}
    except Exception as exc:
        return {"ok": False, "reason": "network_error", "error": str(exc)}


def fetch_with_fallback(url: str, timeout: int, max_bytes: int) -> dict[str, Any]:
    for attempt in range(1, 3):
        attempt_timeout = timeout if attempt == 1 else min(timeout + 10, 30)
        result = fetch_via_firecrawl(url, attempt_timeout)
        result["attempt"] = attempt
        if result.get("ok"):
            return result
        if not result.get("retryable"):
            return fetch_url_python(url, timeout, max_bytes)
        if attempt < 2:
            time.sleep(1)

    py_result = fetch_url_python(url, timeout, max_bytes)
    py_result["primary_error"] = result.get("reason", "retry_exhausted")
    return py_result


def make_run_dir(now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    day_dir = HISTORY_DIR / now.strftime("%Y-%m-%d")
    stem = now.strftime("%H%M%S")
    suffixes = [""] + [f"-{index:02d}" for index in range(1, 100)]
    for suffix in suffixes:
        run_dir = day_dir / f"{stem}{suffix}"
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not create a unique run directory under {day_dir}")


# Output helpers
def _single_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def write_source_text(run_dir: Path, index: int, title: str, url: str, text: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    path = run_dir / "sources" / f"{index:03d}-{digest}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"SOURCE_TITLE: {_single_line(title)}\n"
        f"SOURCE_URL: {_single_line(url)}\n\n"
        "--- CONTENT ---\n\n"
        f"{text.rstrip()}\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def load_collect_templates() -> dict[str, Any]:
    data = json.loads(OUTPUT_TEMPLATES_PATH.read_text(encoding="utf-8"))
    steps = data.get("steps", {})
    templates = steps.get("collect_sources", {}) if isinstance(steps, dict) else {}
    if not isinstance(templates, dict):
        raise RuntimeError("Invalid collect_sources output templates")
    return templates


def render_collect_output(template_name: str, run_dir: Path | None = None) -> dict[str, Any]:
    templates = load_collect_templates()
    template = templates.get(template_name)
    if not isinstance(template, dict):
        raise RuntimeError(f"Missing collect_sources output template: {template_name}")
    rendered: dict[str, Any] = {}
    for key, value in template.items():
        if isinstance(value, str) and run_dir is not None:
            rendered[key] = value.replace("{run_dir}", str(run_dir))
        else:
            rendered[key] = value
    return rendered


# Source collection
def collect_sources(
    topic: str,
    *,
    run_dir: Path | None = None,
    limit_per_call: int = 10,
    target_fetched: int = 5,
    search_timeout: int = 30,
    fetch_timeout: int = 20,
    max_fetch_bytes: int = 500_000,
    min_text_chars: int = 400,
    searchers: tuple = (search_via_exa, search_via_brave),
) -> dict[str, Any]:
    source_files: list[Path] = []
    seen_urls: set[str] = set()
    run_dir = run_dir or make_run_dir()

    items, search_engine, provider_responded = run_search_chain(
        topic, limit_per_call, search_timeout, searchers
    )
    search_failed = not provider_responded

    for item in items:
        if len(source_files) >= target_fetched:
            break

        raw_url = str(item.get("url", "")).strip()
        if not raw_url:
            continue

        canonical = canonical_url(raw_url)
        viable, _reason = is_viable_url(canonical)
        if not viable:
            continue

        if canonical in seen_urls:
            continue

        seen_urls.add(canonical)

        fetch_result = fetch_with_fallback(canonical, fetch_timeout, max_fetch_bytes)
        text = fetch_result.pop("text", "")
        if not fetch_result.get("ok"):
            continue
        if len(text) < min_text_chars:
            continue

        idx = len(source_files) + 1
        text_file = write_source_text(run_dir, idx, item.get("title", ""), canonical, text)
        source_files.append(text_file)

    if source_files:
        template_name = "success_with_sources"
    elif search_failed:
        template_name = "search_provider_failed"
    else:
        template_name = "no_usable_sources"
    result = render_collect_output(template_name, run_dir)
    result["search_engine"] = search_engine
    return result


# CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Morning Report sources via direct search/fetch APIs")
    parser.add_argument("--topic", help="Collect sources for one configured topic.")
    parser.add_argument("--limit-per-call", type=int, default=10)
    parser.add_argument("--target-fetched", type=int, default=5)
    parser.add_argument("--search-timeout", type=int, default=30)
    parser.add_argument("--fetch-timeout", type=int, default=20)
    parser.add_argument("--max-fetch-bytes", type=int, default=500_000)
    parser.add_argument("--min-text-chars", type=int, default=400)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_status = check_topic_config(CONFIG_PATH)
    if not config_status["configured"]:
        result = render_collect_output("config_missing")
        result["available_config"] = config_status["available_config"]
        result["missing_config"] = config_status["missing_config"]
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    configured_topics = [t["topic"] for t in config_status["available_config"]["topics"]]
    topic = _single_line(args.topic) if args.topic else ""
    if not topic:
        if len(configured_topics) != 1:
            result = render_collect_output("multiple_topics")
            result["topics"] = configured_topics
            result["available_config"] = config_status["available_config"]
            result["missing_config"] = config_status["missing_config"]
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            return 0
        topic = configured_topics[0]
    elif topic.casefold() not in {configured_topic.casefold() for configured_topic in configured_topics}:
        result = render_collect_output("topic_not_configured")
        result["topic"] = topic
        result["topics"] = configured_topics
        result["available_config"] = config_status["available_config"]
        result["missing_config"] = config_status["missing_config"]
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    try:
        result = collect_sources(
            topic=topic,
            limit_per_call=args.limit_per_call,
            target_fetched=args.target_fetched,
            search_timeout=args.search_timeout,
            fetch_timeout=args.fetch_timeout,
            max_fetch_bytes=args.max_fetch_bytes,
            min_text_chars=args.min_text_chars,
        )
        result["topic"] = topic
        result["available_config"] = config_status["available_config"]
        result["missing_config"] = config_status["missing_config"]
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
