#!/usr/bin/env python3
"""Generate Morning Report MP3 audio with Google TTS.

This helper turns a clean spoken script into an MP3 file and records a runtime
history manifest for debugging scheduled Morning Reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPORT_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tts_languages import resolve_tts_language  # noqa: E402

DEFAULT_HISTORY_DIR = SKILL_DIR / "state" / "history"
GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
DEFAULT_CHUNK_LIMIT = 180
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_MIN_WORDS = 450
DEFAULT_MAX_WORDS = 750
DEFAULT_WORDS_PER_MINUTE = 150
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
NATURAL_BREAK_RE = re.compile(r"([,;:，；：、])")
WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def audio_length_info(text: str, min_words: int, max_words: int, wpm: int) -> dict[str, Any]:
    word_count = count_words(text)
    estimated_minutes = round(word_count / wpm, 2) if wpm > 0 else None
    warnings: list[str] = []
    if min_words > 0 and word_count < min_words:
        warnings.append(f"under_min_words: {word_count} < {min_words}")
    if max_words > 0 and word_count > max_words:
        warnings.append(f"over_max_words: {word_count} > {max_words}")
    return {
        "word_count": word_count,
        "estimated_minutes": estimated_minutes,
        "target_min_words": min_words,
        "target_max_words": max_words,
        "words_per_minute": wpm,
        "length_ok": not warnings,
        "length_warnings": warnings,
    }


def split_sentences(paragraph: str) -> list[str]:
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(paragraph) if part.strip()]


def split_on_natural_breaks(text: str) -> list[str]:
    tokens = NATURAL_BREAK_RE.split(text)
    parts: list[str] = []
    current = ""
    delimiters = {",", ";", ":", "，", "；", "：", "、"}
    for token in tokens:
        if not token:
            continue
        if token in delimiters:
            current += token
            if current.strip():
                parts.append(current.strip())
            current = ""
        else:
            if current.strip():
                parts.append(current.strip())
            current = token.strip()
    if current.strip():
        parts.append(current.strip())
    return parts or [text.strip()]


def wrap_words(text: str, limit: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[i : i + limit] for i in range(0, len(word), limit))
            continue
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def split_long_segment(segment: str, limit: int) -> list[str]:
    segment = segment.strip()
    if len(segment) <= limit:
        return [segment] if segment else []

    pieces: list[str] = []
    current = ""
    for part in split_on_natural_breaks(segment):
        if len(part) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(wrap_words(part, limit))
            continue
        candidate = part if not current else f"{current} {part}"
        if len(candidate) <= limit:
            current = candidate
        else:
            pieces.append(current)
            current = part
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, limit: int) -> list[str]:
    if limit < 50:
        raise ValueError("chunk limit must be at least 50 characters")
    normalized = normalize_text(text)
    if not normalized:
        raise ValueError("audio text is empty")

    segments: list[str] = []
    for paragraph in re.split(r"\n+", normalized):
        segments.extend(split_sentences(paragraph))

    chunks: list[str] = []
    current = ""
    for segment in segments:
        for piece in split_long_segment(segment, limit):
            candidate = piece if not current else f"{current} {piece}"
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = piece
    if current:
        chunks.append(current)

    too_long = [chunk for chunk in chunks if len(chunk) > limit]
    if too_long:
        raise ValueError(f"internal split error: chunk exceeds limit ({len(too_long[0])}>{limit})")
    return chunks


def read_input_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def choose_transport(transport: str) -> str:
    if transport != "auto":
        return transport
    return "curl" if shutil.which("curl") else "urllib"


def curl_tts(text: str, lang: str, output: Path, timeout: int, retries: int) -> None:
    cmd = [
        "curl",
        "-fsSL",
        "--retry",
        str(retries),
        "--connect-timeout",
        "15",
        "--max-time",
        str(timeout),
        "-A",
        DEFAULT_USER_AGENT,
        "--get",
        GOOGLE_TTS_URL,
        "--data-urlencode",
        "ie=UTF-8",
        "--data-urlencode",
        "client=tw-ob",
        "--data-urlencode",
        f"tl={lang}",
        "--data-urlencode",
        f"q={text}",
        "--output",
        str(output),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"curl exited {completed.returncode}"
        raise RuntimeError(detail)


def urllib_tts(text: str, lang: str, output: Path, timeout: int) -> None:
    params = urllib.parse.urlencode(
        {
            "ie": "UTF-8",
            "client": "tw-ob",
            "tl": lang,
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"{GOOGLE_TTS_URL}?{params}",
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            output.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Google TTS HTTP {exc.code}: {body}") from exc


def validate_audio_file(path: Path) -> int:
    size = path.stat().st_size if path.exists() else 0
    if size < 256:
        raise RuntimeError(f"TTS output is missing or too small: {path} ({size} bytes)")
    return size


def generate_chunk_audio(
    text: str,
    lang: str,
    output: Path,
    transport: str,
    timeout: int,
    retries: int,
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    if transport == "curl":
        curl_tts(text, lang, output, timeout, retries)
    elif transport == "urllib":
        urllib_tts(text, lang, output, timeout)
    else:
        raise ValueError(f"unsupported transport: {transport}")
    return validate_audio_file(output)


def ffmpeg_concat_list(paths: list[Path], list_path: Path) -> None:
    lines = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge_audio(chunks: list[Path], output: Path, run_dir: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    if len(chunks) == 1:
        shutil.copyfile(chunks[0], output)
        validate_audio_file(output)
        return "single_file_copy"

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        list_path = run_dir / "ffmpeg-list.txt"
        ffmpeg_concat_list(chunks, list_path)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode == 0:
            validate_audio_file(output)
            return "ffmpeg_concat_copy"

    with output.open("wb") as merged:
        for path in chunks:
            merged.write(path.read_bytes())
    validate_audio_file(output)
    return "binary_append_fallback"


def speed_metadata(speed: float) -> dict[str, Any]:
    supported = speed == 1.0 or shutil.which("ffmpeg") is not None
    return {
        "speed": speed,
        "speed_supported": supported,
        "speed_applied": False,
        "speed_method": "none" if speed == 1.0 else "ffmpeg_atempo",
    }


def apply_audio_speed(path: Path, speed: float, run_dir: Path) -> dict[str, Any]:
    info = speed_metadata(speed)
    if speed == 1.0:
        return info
    if not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        info["speed_warning"] = "ffmpeg_missing_speed_not_applied"
        return info

    temp_output = run_dir / f".{path.stem}-speed-adjusted.tmp{path.suffix}"
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-filter:a",
        f"atempo={speed:g}",
        str(temp_output),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        temp_output.unlink(missing_ok=True)
        info["speed_warning"] = completed.stderr.strip() or f"ffmpeg exited {completed.returncode}"
        return info

    validate_audio_file(temp_output)
    shutil.move(str(temp_output), str(path))
    validate_audio_file(path)
    info["speed_applied"] = True
    return info


def make_run_dir(history_dir: Path, text: str, now: datetime) -> Path:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    date_dir = history_dir / now.strftime("%Y-%m-%d")
    base_name = f"{now.strftime('%H%M%S')}-{digest}"
    candidate = date_dir / base_name
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = date_dir / f"{base_name}-{suffix}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    (run_dir / "audio-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_audio(
    *,
    text_file: str,
    lang: str,
    output: str | None = None,
    history_dir: str | Path = DEFAULT_HISTORY_DIR,
    run_dir: str | Path | None = None,
    chunk_limit: int = DEFAULT_CHUNK_LIMIT,
    transport: str = "auto",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
    wpm: int = DEFAULT_WORDS_PER_MINUTE,
    speed: float = 1.0,
    strict_length: bool = False,
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    created_at = now or datetime.now(timezone.utc)
    history_run_dir: Path | None = None
    try:
        raw_text = read_input_text(text_file)
        text = normalize_text(raw_text)
        chunks = split_text(text, chunk_limit)
        selected_transport = choose_transport(transport)
        language_check = resolve_tts_language(lang)
        if not language_check["ok"]:
            raise ValueError(
                f"unsupported_tts_language: {lang!r}; status={language_check['status']}"
            )
        tts_lang = str(language_check["lang"])
        length = audio_length_info(text, min_words, max_words, wpm)
        speed_info = speed_metadata(speed)
        if not 0.5 <= speed <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        if strict_length and not length["length_ok"]:
            raise ValueError("audio_length_out_of_range: " + "; ".join(length["length_warnings"]))

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "lang": tts_lang,
                "requested_lang": lang,
                "chunk_limit": chunk_limit,
                "chunk_count": len(chunks),
                "char_count": len(text),
                **speed_info,
                **length,
                "chunks": chunks,
            }

        if run_dir is not None:
            history_run_dir = Path(run_dir)
            history_run_dir.mkdir(parents=True, exist_ok=True)
        else:
            history_run_dir = make_run_dir(Path(history_dir), text, created_at)
        (history_run_dir / "audio-script.txt").write_text(text + "\n", encoding="utf-8")
        chunks_dir = history_run_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        chunk_paths: list[Path] = []
        chunk_manifest: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks, 1):
            chunk_path = chunks_dir / f"chunk-{index:03d}.mp3"
            size = generate_chunk_audio(
                chunk,
                tts_lang,
                chunk_path,
                selected_transport,
                timeout,
                retries,
            )
            chunk_paths.append(chunk_path)
            chunk_manifest.append(
                {
                    "index": index,
                    "file": str(chunk_path.relative_to(history_run_dir)),
                    "characters": len(chunk),
                    "bytes": size,
                    "text": chunk,
                }
            )

        history_output = history_run_dir / "morning-report.mp3"
        merge_method = merge_audio(chunk_paths, history_output, history_run_dir)
        speed_info = apply_audio_speed(history_output, speed, history_run_dir)
        final_output = Path(output) if output else history_output
        if final_output.resolve() != history_output.resolve():
            final_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(history_output, final_output)
            validate_audio_file(final_output)

        manifest = {
            "success": True,
            "created_at": created_at.isoformat(),
            "lang": tts_lang,
            "requested_lang": lang,
            "chunk_limit": chunk_limit,
            "transport": selected_transport,
            "merge_method": merge_method,
            **speed_info,
            "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "char_count": len(text),
            **length,
            "chunk_count": len(chunks),
            "history_dir": str(history_run_dir),
            "history_audio": str(history_output),
            "output": str(final_output),
            "output_bytes": final_output.stat().st_size,
            "chunks": chunk_manifest,
        }
        write_manifest(history_run_dir, manifest)
        return manifest
    except Exception as exc:
        if history_run_dir is not None:
            write_manifest(
                history_run_dir,
                {
                    "success": False,
                    "created_at": created_at.isoformat(),
                    "error": str(exc),
                },
            )
        raise


def apply_audio_generation_result(
    *,
    state: dict[str, Any],
    work_dir: Path,
    audio: dict[str, Any],
    manifest: dict[str, Any] | None,
    error: str,
) -> tuple[bool, dict[str, Any]]:
    from report.common import runner_command, save_run_state

    if manifest and manifest.get("success"):
        manifest_path = str(Path(manifest["history_dir"]) / "audio-manifest.json")
        audio.update(
            {
                "status": "generated",
                "file": manifest["output"],
                "manifest": manifest_path,
                "generation": manifest,
            }
        )
        next_action = {
            "type": "send_audio",
            "media_line": f"MEDIA:{manifest['output']}",
            "message_goal": "Send one standalone MEDIA line for Telegram.",
            "next_command": runner_command("record-audio", work_dir, "--audio-status", "sent", "--send-status", "sent"),
        }
        success = True
    else:
        audio.update(
            {
                "status": "failed",
                "failure_reason": "audio_generation_failed",
                "error": error,
            }
        )
        next_action = {
            "type": "audio_failed_notice",
            "message_goal": "Tell the user the text report was sent but audio generation failed.",
            "next_command": runner_command("record-audio", work_dir, "--audio-status", "failed", "--send-status", "failure_notice_sent"),
        }
        success = False

    state["next_action"] = next_action
    save_run_state(work_dir, state)
    return success, next_action


def generate_audio_phase(args: argparse.Namespace) -> dict[str, Any]:
    from report.common import load_run_state

    work_dir = Path(args.work_dir)
    state = load_run_state(work_dir)
    audio_script_file = Path(args.audio_script_file or state["audio_script_file"])
    output_file = Path(args.audio_file or state["audio_file"])
    audio = state.setdefault("audio", {})
    manifest: dict[str, Any] | None = None
    error = ""
    try:
        history_run_dir = state.get("history", {}).get("run_dir")
        manifest = generate_audio(
            text_file=str(audio_script_file),
            output=str(output_file),
            lang=state["config"]["report_language"],
            run_dir=history_run_dir,
            speed=args.speed,
            min_words=args.min_words,
            max_words=args.max_words,
            wpm=args.wpm,
            chunk_limit=args.chunk_limit,
            strict_length=True,
        )
    except Exception as exc:
        error = str(exc)

    success, next_action = apply_audio_generation_result(
        state=state,
        work_dir=work_dir,
        audio=audio,
        manifest=manifest,
        error=error,
    )
    return {
        "success": success,
        "phase": "generate-audio",
        "can_continue": success,
        "work_dir": str(work_dir),
        "audio_file": str(output_file),
        "config": state["config"],
        "audio": audio,
        "next_action": next_action,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Morning Report MP3 audio")
    parser.add_argument("--text-file", required=True, help="Text file to synthesize, or '-' for stdin")
    parser.add_argument("--output", help="Final MP3 output path. Defaults to the history run directory")
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), help="Audio history directory")
    parser.add_argument(
        "--lang",
        required=True,
        help="Configured report language or Google TTS language code, for example English or en",
    )
    parser.add_argument("--chunk-limit", type=int, default=DEFAULT_CHUNK_LIMIT, help="Max characters per TTS request")
    parser.add_argument("--transport", choices=["auto", "curl", "urllib"], default="auto")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--retries", type=int, default=2, help="curl retry count")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    parser.add_argument("--wpm", type=int, default=DEFAULT_WORDS_PER_MINUTE, help="Words per minute for duration estimate")
    parser.add_argument("--speed", type=float, default=1.0, help="Best-effort MP3 playback speed. Uses ffmpeg when available.")
    parser.add_argument("--strict-length", action="store_true", help="Fail when text is outside the target word range")
    parser.add_argument("--dry-run", action="store_true", help="Split text and print planned chunks without calling TTS")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = generate_audio(
            text_file=args.text_file,
            output=args.output,
            history_dir=args.history_dir,
            lang=args.lang,
            chunk_limit=args.chunk_limit,
            transport=args.transport,
            timeout=args.timeout,
            retries=args.retries,
            min_words=args.min_words,
            max_words=args.max_words,
            wpm=args.wpm,
            speed=args.speed,
            strict_length=args.strict_length,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"report/generate_audio_file.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
