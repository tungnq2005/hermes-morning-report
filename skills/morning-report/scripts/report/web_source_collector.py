#!/usr/bin/env python3
"""Collect Morning Report sources through search, dedupe, freshness validation, and fetch."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("/tmp/morning-report-search-fetch-probe")
DEFAULT_TARGET_FETCHED = 5
DEFAULT_FRESHNESS_HOURS = 24
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
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
LOGIN_HOST_MARKERS = {
    "accounts.google.com",
    "login.",
    "signin.",
}
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
UNTRUSTED_RE = re.compile(r"<<<EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>|<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        if tag.lower() in {"p", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        if tag.lower() in {"p", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
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


def clean_external_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = UNTRUSTED_RE.sub("", text)
    text = text.replace("Source: Web Search", "")
    text = text.replace("---", "")
    return html.unescape(re.sub(r"\s+", " ", text).strip())


def canonical_url(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(
        [(key, value) for key, value in query_pairs if key.lower() not in TRACKING_PARAMS],
        doseq=True,
    )
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


def hostname(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def is_social_url(url: str) -> bool:
    host = hostname(url)
    return any(host == social or host.endswith(f".{social}") for social in SOCIAL_HOSTS)


def is_viable_url(url: str, *, include_social: bool) -> tuple[bool, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_scheme"
    host = parsed.netloc.lower()
    if not host:
        return False, "missing_host"
    if any(marker in host for marker in LOGIN_HOST_MARKERS):
        return False, "login_host"
    if is_social_url(url) and not include_social:
        return False, "social_skipped"
    suffix = Path(parsed.path).suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        return False, f"blocked_extension:{suffix}"
    return True, "ok"


def parse_datetime(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    relative = re.match(r"^(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago$", text, re.I)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        now = datetime.now(timezone.utc)
        days = {
            "minute": amount / 1440,
            "hour": amount / 24,
            "day": amount,
            "week": amount * 7,
            "month": amount * 30,
            "year": amount * 365,
        }[unit]
        return (now - timedelta(days=days)).isoformat()

    normalized = text.replace("Z", "+00:00")
    for candidate in [normalized, normalized[:10]]:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def extract_published_at(item: dict[str, Any]) -> tuple[str | None, str]:
    for key in ["published_at", "publishedAt", "datePublished", "date", "age", "published"]:
        value = item.get(key)
        parsed = parse_datetime(value)
        if parsed:
            return parsed, key
    return None, "missing"


def freshness_status(published_at: str | None, freshness_hours: int) -> str:
    if published_at is None:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(published_at)
    except ValueError:
        return "unknown"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=freshness_hours)
    return "valid_24h" if parsed >= cutoff else "stale"


def validate_search_freshness(candidate: dict[str, Any], freshness_hours: int) -> tuple[bool, str]:
    published_at = candidate.get("search_published_at")
    if not published_at:
        return False, "missing_publish_time"
    status = freshness_status(str(published_at), freshness_hours)
    if status != "valid_24h":
        return False, "outside_freshness_window"
    return True, "ok"


def run_search(query: str, limit: int, provider: str | None, timeout: int) -> dict[str, Any]:
    cmd = ["openclaw", "infer", "web", "search", "--query", query, "--limit", str(limit), "--json"]
    if provider:
        cmd.extend(["--provider", provider])
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"search failed: {query}")
    return json.loads(completed.stdout)


def search_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for output in payload.get("outputs", []):
        result = output.get("result", {}) if isinstance(output, dict) else {}
        items = result.get("results", [])
        if isinstance(items, list):
            results.extend(item for item in items if isinstance(item, dict))
    return results


def query_plan(topic: str | None, queries: list[str], max_calls: int) -> list[str]:
    if queries:
        return queries[:max_calls]
    if not topic:
        raise ValueError("provide --topic or at least one --query")
    base = topic.strip()
    planned = [
        base,
        f"{base} latest news",
        f"{base} today",
        f"{base} market update",
        f"{base} analysis",
    ]
    return planned[:max_calls]


def search_candidate(
    item: dict[str, Any],
    query: str,
    *,
    include_social: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_url = str(item.get("url", "")).strip()
    if not raw_url:
        return None, {"query": query, "reason": "missing_url", "item": item}
    canonical = canonical_url(raw_url)
    viable, reason = is_viable_url(canonical, include_social=include_social)
    if not viable:
        return None, {"query": query, "url": raw_url, "canonical_url": canonical, "reason": reason}
    published_at, published_source = extract_published_at(item)
    return {
        "query": query,
        "title": clean_external_text(item.get("title")),
        "url": raw_url,
        "canonical_url": canonical,
        "description": clean_external_text(item.get("description")),
        "site_name": clean_external_text(item.get("siteName") or item.get("site_name")),
        "search_published_at": published_at,
        "search_published_source": published_source,
        "host": hostname(canonical),
    }, None


def fetch_candidate(
    candidate: dict[str, Any],
    args: argparse.Namespace,
    output_dir: Path,
    source_index: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    viable, reason = is_viable_url(candidate["canonical_url"], include_social=args.include_social)
    if not viable:
        return None, {**candidate, "reason": reason}

    result = fetch_url(candidate["canonical_url"], args.fetch_timeout, args.max_fetch_bytes)
    text = result.pop("text", "")
    if not result.get("ok"):
        return None, {**candidate, "reason": "fetch_failed", "fetch": result}
    if len(text) < args.min_text_chars:
        return None, {
            **candidate,
            "reason": "fetched_text_too_short",
            "fetch": {**result, "text_char_count": len(text)},
        }

    published_at = candidate["search_published_at"]
    published_basis = "search_metadata"
    text_file = write_fetch_text(output_dir, source_index, candidate["canonical_url"], text)
    return {
        **candidate,
        "published_at": published_at,
        "published_basis": published_basis,
        "freshness_status": freshness_status(published_at, args.freshness_hours),
        "fetch": {
            **result,
            "text_char_count": len(text),
            "text_file": text_file,
        },
    }, None


def collect_sources_incrementally(
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    search_runs: list[dict[str, Any]] = []
    seen: set[str] = set()

    for query in query_plan(args.topic, args.query or [], args.max_search_calls):
        payload = run_search(query, args.limit_per_call, args.provider, args.search_timeout)
        items = search_results(payload)
        run = {
            "query": query,
            "result_count": len(items),
            "new_candidate_count": 0,
            "fetched_source_count_before": len(sources),
            "stopped_after_target": False,
        }

        for item in items:
            candidate, rejection = search_candidate(item, query, include_social=args.include_social)
            if rejection is not None:
                rejected.append(rejection)
                continue
            if candidate is None:
                continue

            canonical = candidate["canonical_url"]
            if canonical in seen:
                rejected.append({**candidate, "reason": "duplicate"})
                continue

            seen.add(canonical)
            valid_freshness, freshness_reason = validate_search_freshness(candidate, args.freshness_hours)
            if not valid_freshness:
                rejected.append({**candidate, "reason": freshness_reason})
                continue

            candidates.append(candidate)
            run["new_candidate_count"] += 1

            source, fetch_rejection = fetch_candidate(candidate, args, output_dir, len(sources) + 1)
            if fetch_rejection is not None:
                rejected.append(fetch_rejection)
                continue
            if source is not None:
                sources.append(source)

            if len(sources) >= args.target_fetched:
                run["stopped_after_target"] = True
                break

        run["fetched_source_count_after"] = len(sources)
        search_runs.append(run)
        if len(sources) >= args.target_fetched:
            break

    return sources, rejected, search_runs, candidates


def decode_body(data: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset=([^;\s]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def html_to_text(raw: str) -> str:
    extractor = TextExtractor()
    extractor.feed(raw)
    return extractor.text()


def fetch_url(url: str, timeout: int, max_bytes: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            content_type = response.headers.get("content-type", "")
            truncated = len(data) > max_bytes
            if truncated:
                data = data[:max_bytes]
            raw = decode_body(data, content_type)
            text = html_to_text(raw) if "html" in content_type.lower() or "<html" in raw[:500].lower() else raw.strip()
            return {
                "ok": True,
                "status_code": getattr(response, "status", None),
                "final_url": response.geturl(),
                "content_type": content_type,
                "bytes_read": len(data),
                "truncated": truncated,
                "text": text,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": f"HTTP {exc.code}", "final_url": exc.geturl()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def write_fetch_text(output_dir: Path, index: int, url: str, text: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    path = output_dir / "fetched-text" / f"{index:03d}-{digest}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return str(path)


def source_brief(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": source.get("title", ""),
        "url": source.get("canonical_url", ""),
        "host": source.get("host", ""),
        "site_name": source.get("site_name", ""),
        "published_at": source.get("published_at"),
        "published_basis": source.get("published_basis"),
        "freshness_status": source.get("freshness_status"),
        "text_file": source.get("fetch", {}).get("text_file"),
        "text_char_count": source.get("fetch", {}).get("text_char_count", 0),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Morning Report search + fetch sources")
    parser.add_argument("--topic", help="Topic used to build default search queries")
    parser.add_argument("--query", action="append", help="Explicit search query; repeat for multiple queries")
    parser.add_argument("--provider", default="brave")
    parser.add_argument("--target-fetched", type=int, default=DEFAULT_TARGET_FETCHED, help="Stop after this many successfully fetched readable web sources")
    parser.add_argument("--max-search-calls", type=int, default=5)
    parser.add_argument("--limit-per-call", type=int, default=10)
    parser.add_argument("--freshness-hours", type=int, default=DEFAULT_FRESHNESS_HOURS)
    parser.add_argument("--include-social", action="store_true")
    parser.add_argument("--search-timeout", type=int, default=30)
    parser.add_argument("--fetch-timeout", type=int, default=20)
    parser.add_argument("--max-fetch-bytes", type=int, default=500_000)
    parser.add_argument("--min-text-chars", type=int, default=400)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--summary", action="store_true", help="Print only summary fields; full manifest is still saved")
    parser.add_argument("--compact", action="store_true")
    return parser


def summary_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": manifest["success"],
        "topic": manifest["topic"],
        "queries": manifest["queries"],
        "queries_attempted": manifest.get("queries_attempted", []),
        "search_calls_used": manifest.get("search_calls_used", 0),
        "max_search_calls": manifest.get("max_search_calls", 0),
        "limit_per_call": manifest.get("limit_per_call", 0),
        "candidate_count": manifest.get("candidate_count", 0),
        "target_fetched": manifest["target_fetched"],
        "source_count": manifest["source_count"],
        "fresh_24h_count": manifest["fresh_24h_count"],
        "rejected_count": manifest["rejected_count"],
        "filters": manifest["filters"],
        "manifest_path": manifest["manifest_path"],
        "fetched_text_dir": str(Path(manifest["manifest_path"]).parent / "fetched-text"),
        "source_hosts": sorted({item["host"] for item in manifest["sources"]}),
        "fetched_sources": manifest["fetched_sources"],
    }


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        sources, rejected, search_runs, candidates = collect_sources_incrementally(args, output_dir)
        fetched_sources = [source_brief(source) for source in sources]
        manifest = {
            "success": len(sources) >= args.target_fetched,
            "topic": args.topic,
            "queries": query_plan(args.topic, args.query or [], args.max_search_calls),
            "queries_attempted": [run["query"] for run in search_runs],
            "search_calls_used": len(search_runs),
            "max_search_calls": args.max_search_calls,
            "limit_per_call": args.limit_per_call,
            "candidate_count": len(candidates),
            "target_fetched": args.target_fetched,
            "source_count": len(sources),
            "fresh_24h_count": sum(1 for source in sources if source.get("freshness_status") == "valid_24h"),
            "rejected_count": len(rejected),
            "filters": {
                "freshness_hours": args.freshness_hours,
                "include_social": args.include_social,
                "min_text_chars": args.min_text_chars,
            },
            "fetched_sources": fetched_sources,
            "sources": sources,
            "search_runs": search_runs,
            "rejected_sample": rejected[:50],
        }
        manifest_path = output_dir / "manifest.json"
        manifest["manifest_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.summary:
            manifest = summary_manifest(manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=None if args.compact else 2))
        return 0
    except Exception as exc:
        print(f"web_source_collector.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
