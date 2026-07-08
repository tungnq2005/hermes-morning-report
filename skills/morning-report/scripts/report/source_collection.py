"""Search, dedupe, fetch, and freshness phases."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from report import web_source_collector
from report.common import (
    DEFAULT_AUDIO_FILE,
    DEFAULT_AUDIO_SCRIPT_FILE,
    DEFAULT_REPORT_FILE,
    config_from_status,
    configured_topics,
    ensure_runnable_config,
    load_run_state,
    query_topic,
    runner_command,
    save_run_state,
    stop_result,
    utc_now,
    read_json,
    write_json,
)


def source_briefs(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [web_source_collector.source_brief(source) for source in sources]


def failed_fetch_urls(rejected: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in rejected:
        if item.get("reason") != "fetch_failed":
            continue
        url = item.get("canonical_url") or item.get("url")
        if isinstance(url, str) and url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def search_manifest(*, args: argparse.Namespace, work_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    topics = configured_topics(status)
    topic_text = query_topic(topics)
    if not topic_text:
        raise ValueError("missing configured topics")

    queries = web_source_collector.query_plan(topic_text, args.query or [], args.max_search_calls)
    manifest = {
        "success": True,
        "created_at": utc_now(),
        "topic": topic_text,
        "topics": topics,
        "queries": queries,
        "query_overrides": args.query or [],
        "provider": args.provider,
        "fallback_provider": args.fallback_provider,
        "max_search_calls": args.max_search_calls,
        "limit_per_call": args.limit_per_call,
        "search_timeout": args.search_timeout,
        "filters": {"include_social": args.include_social},
    }
    manifest_path = work_dir / "search" / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def source_manifest_from_search_plan(*, args: argparse.Namespace, work_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    search_path = Path(state["search_collection"]["manifest_path"])
    search_data = read_json(search_path)

    collect_args = argparse.Namespace(
        topic=search_data.get("topic"),
        query=search_data.get("query_overrides", []),
        provider=search_data.get("provider", "brave"),
        fallback_provider=search_data.get("fallback_provider", "exa"),
        max_search_calls=int(search_data.get("max_search_calls", 5)),
        limit_per_call=int(search_data.get("limit_per_call", 10)),
        search_timeout=int(search_data.get("search_timeout", 30)),
        target_fetched=args.target_fetched,
        fetch_timeout=args.fetch_timeout,
        max_fetch_bytes=args.max_fetch_bytes,
        min_text_chars=args.min_text_chars,
        include_social=bool(args.include_social or search_data.get("filters", {}).get("include_social")),
        freshness_hours=args.freshness_hours,
    )
    sources, rejected, search_runs, candidates = web_source_collector.collect_sources_incrementally(
        collect_args,
        work_dir / "sources",
    )
    fetched_sources = source_briefs(sources)
    manifest = {
        "success": len(sources) >= args.target_fetched,
        "created_at": utc_now(),
        "topic": search_data.get("topic"),
        "topics": search_data.get("topics", []),
        "search_manifest_path": str(search_path),
        "queries": search_data.get("queries", []),
        "queries_attempted": [run["query"] for run in search_runs],
        "search_calls_used": len(search_runs),
        "max_search_calls": collect_args.max_search_calls,
        "limit_per_call": collect_args.limit_per_call,
        "primary_search_provider": collect_args.provider,
        "fallback_search_provider": collect_args.fallback_provider,
        "search_fallback_used": any(bool(run.get("fallback_used")) for run in search_runs),
        "candidate_count": len(candidates),
        "target_fetched": args.target_fetched,
        "source_count": len(sources),
        "fresh_24h_count": sum(1 for source in sources if source.get("freshness_status") == "valid_24h"),
        "failed_fetch_urls": failed_fetch_urls(rejected),
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
    manifest_path = work_dir / "sources" / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def search_phase(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    status, stop = ensure_runnable_config(args, work_dir, "search")
    if stop is not None:
        return stop

    manifest = search_manifest(args=args, work_dir=work_dir, status=status)
    can_continue = True
    config = config_from_status(status)
    result = {
        "success": can_continue,
        "phase": "search",
        "can_continue": can_continue,
        "created_at": utc_now(),
        "work_dir": str(work_dir),
        "report_file": str(Path(args.report_file or DEFAULT_REPORT_FILE)),
        "audio_script_file": str(Path(args.audio_script_file or DEFAULT_AUDIO_SCRIPT_FILE)),
        "audio_file": str(Path(args.audio_file or DEFAULT_AUDIO_FILE)),
        "config": config,
        "search_collection": {
            "status": "planned",
            "manifest_path": manifest["manifest_path"],
            "max_search_calls": manifest["max_search_calls"],
            "limit_per_call": manifest["limit_per_call"],
            "primary_search_provider": manifest["provider"],
            "fallback_search_provider": manifest["fallback_provider"],
            "planned_query_count": len(manifest["queries"]),
        },
        "audio": {
            "enabled": config["audio_enabled"],
            "status": "pending" if config["audio_enabled"] else "disabled",
        },
        "next_action": (
            {
                "type": "fetch_sources",
                "command": runner_command("fetch", work_dir),
                "message_goal": "Search one query at a time, dedupe URLs, keep only 24h-valid URLs, fetch readable sources, and stop when enough sources are collected.",
            }
        ),
    }
    save_run_state(work_dir, result)
    return result


def fetch_phase(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    if "search_collection" not in state:
        return stop_result(
            phase="fetch",
            work_dir=work_dir,
            reason="missing_search_collection",
            message_goal="Tell the user source search was not completed before fetch.",
        )

    source_manifest = source_manifest_from_search_plan(args=args, work_dir=work_dir, state=state)
    source_count = source_manifest["source_count"]
    can_continue = source_count >= args.target_fetched
    source_status = "ok" if source_count >= args.target_fetched else "limited"
    if source_count == 0:
        source_status = "blocked"

    result = {
        "success": can_continue,
        "phase": "fetch",
        "can_continue": can_continue,
        "created_at": utc_now(),
        "work_dir": str(work_dir),
        "report_file": state["report_file"],
        "audio_script_file": state["audio_script_file"],
        "audio_file": state["audio_file"],
        "config": state["config"],
        "search_collection": state["search_collection"],
        "source_collection": {
            "status": source_status,
            "manifest_path": source_manifest["manifest_path"],
            "search_calls_used": source_manifest["search_calls_used"],
            "max_search_calls": source_manifest["max_search_calls"],
            "primary_search_provider": source_manifest["primary_search_provider"],
            "fallback_search_provider": source_manifest["fallback_search_provider"],
            "search_fallback_used": source_manifest["search_fallback_used"],
            "source_count": source_count,
            "target_fetched": source_manifest["target_fetched"],
            "fresh_24h_count": source_manifest["fresh_24h_count"],
            "fetched_sources": source_manifest["fetched_sources"],
            "failed_fetch_count": len(source_manifest["failed_fetch_urls"]),
        },
        "audio": state.get("audio", {}),
        "next_action": (
            {
                "type": "write_report",
                "message_goal": "Write the text report from fetched_sources and save it to report_file.",
                "next_command": runner_command("validate-report", work_dir),
                "instructions": [
                    "Read every fetched_sources text_file before writing.",
                    "Use the fetched sources as the evidence base.",
                    "Use evidence links only from fetched_sources.url values; do not cite links found inside fetched pages.",
                    "Use configured report_language and report_style.",
                    "Use calm, non-sensational wording and no decorative emoji in the report title.",
                ],
                "references": [
                    "skills/morning-report/references/report-styles.md",
                    "skills/morning-report/references/research.md",
                ],
            }
            if can_continue
            else {
                "type": "stop",
                "reason": "not_enough_24h_sources",
                "message_goal": "Tell the user fewer than 5 readable 24h-valid sources were fetched and no report was generated.",
            }
        ),
    }
    save_run_state(work_dir, result)
    return result
