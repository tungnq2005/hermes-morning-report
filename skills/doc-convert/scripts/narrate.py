#!/usr/bin/env python3
"""Produce a narration script from a document, ready for TTS.

Usage:
  python3 narrate.py --input <path-or-url> [--lang Vietnamese] [--min-words 350] [--max-words 700] [--outdir DIR]

Prints JSON: {script_path, word_count, suggested_tts_command}. The actual MP3 is then
generated with the shared TTS helper (morning-report's generate_audio.py), writing into
this skill's audio-history so the result can be attached from the workspace.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_io
from doc_io import DocConvertError

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(os.path.dirname(SKILL_DIR))
TTS_HELPER = os.path.join(WORKSPACE, "skills", "morning-report", "scripts", "generate_audio.py")


def build_script(doc: dict, sections: list[dict], min_words: int, max_words: int) -> str:
    lines = [f"{doc['title']}.", ""]
    for sec in sections:
        if sec["title"]:
            lines.append(f"{sec['title']}.")
        for item in sec["items"]:
            lines.append(item if item.endswith((".", "!", "?")) else item + ".")
        lines.append("")
    words = " ".join(lines).split()
    if len(words) > max_words:
        # keep intro + as many complete lines as fit
        kept: list[str] = []
        count = 0
        for line in lines:
            n = len(line.split())
            if count + n > max_words:
                break
            kept.append(line)
            count += n
        lines = kept + ["", "Hết phần tóm tắt."]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a narration script from a document")
    ap.add_argument("--input", required=True)
    ap.add_argument("--lang", default="Vietnamese")
    ap.add_argument("--min-words", type=int, default=350)
    ap.add_argument("--max-words", type=int, default=700)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    result: dict = {"success": False, "input": args.input}
    try:
        now = datetime.datetime.now()
        run_dir = args.outdir or os.path.join(
            SKILL_DIR, "state", "audio-history",
            now.strftime("%Y-%m-%d"), f"{now.strftime('%H%M%S')}-{secrets.token_hex(4)}")
        os.makedirs(run_dir, exist_ok=True)

        src = args.input
        if doc_io.is_url(src):
            src = doc_io.download(src, os.path.join(run_dir, "input"))
        elif not os.path.exists(src):
            raise DocConvertError(f"Input file not found: {src}")

        doc = doc_io.extract(src)
        sections = doc_io.outline_sections(doc)
        script = build_script(doc, sections, args.min_words, args.max_words)
        script_path = os.path.join(run_dir, "narration-script.txt")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(script)

        word_count = len(script.split())
        result.update({
            "success": True,
            "title": doc["title"],
            "script_path": script_path,
            "word_count": word_count,
            "run_dir": run_dir,
            "warnings": ["script shorter than target; audio may be under 3 minutes"] if word_count < args.min_words else [],
            "suggested_tts_command": (
                f"python3 {TTS_HELPER} --text-file {script_path} "
                f"--history-dir {os.path.join(SKILL_DIR, 'state', 'audio-history')} --lang \"{args.lang}\""
            ),
        })
    except DocConvertError as err:
        result["error"] = str(err)
    except Exception as err:
        result["error"] = f"{type(err).__name__}: {err}"

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
