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

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from helpers.tts_languages import check_tts_language  # noqa: E402
from helpers.history import record_audio_validation  # noqa: E402

GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
DEFAULT_CHUNK_LIMIT = 180
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_MIN_WORDS = 680
DEFAULT_MAX_WORDS = 930
DEFAULT_WORDS_PER_MINUTE = 189
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


def generate_audio(
    *,
    text_file: str,
    lang: str,
    output: str | None = None,
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
    work_dir: Path | None = None
    try:
        raw_text = read_input_text(text_file)
        text = normalize_text(raw_text)
        chunks = split_text(text, chunk_limit)
        selected_transport = choose_transport(transport)
        tts_lang = check_tts_language(lang)["lang"]
        if not tts_lang:
            raise ValueError(f"unsupported_tts_language: {lang!r}")
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

        final_output = Path(output) if output else Path("/tmp/morning-report.mp3")
        final_output.parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path("/tmp/morning-report-audio-chunks")
        work_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir = work_dir / "chunks"
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
                    "file": str(chunk_path.relative_to(work_dir)),
                    "characters": len(chunk),
                    "bytes": size,
                    "text": chunk,
                }
            )

        merge_method = merge_audio(chunk_paths, final_output, work_dir)
        speed_info = apply_audio_speed(final_output, speed, work_dir)

        return {
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
            "output": str(final_output),
            "output_bytes": final_output.stat().st_size,
            "chunks": chunk_manifest,
        }
    except Exception as exc:
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Morning Report MP3 audio")
    parser.add_argument("--text-file", required=True, help="Text file to synthesize, or '-' for stdin")
    parser.add_argument(
        "--output",
        help="Final MP3 output path. Defaults to run_dir/morning-report.mp3 when --run-dir is set, otherwise /tmp/morning-report.mp3",
    )
    parser.add_argument("--run-dir", help="History run directory for recording audio metadata")
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
        output = args.output
        if output is None and args.run_dir and not args.dry_run:
            output = str(Path(args.run_dir) / "morning-report.mp3")
        result = generate_audio(
            text_file=args.text_file,
            output=output,
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
        if args.run_dir and result.get("success") and not result.get("dry_run"):
            audio_meta = record_audio_validation(Path(args.run_dir), Path(str(result["output"])))
            result["audio"] = audio_meta
            result["output"] = str(Path(args.run_dir) / str(audio_meta["file"]))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"report/generate_audio_file.py failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
