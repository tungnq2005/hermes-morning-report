#!/usr/bin/env python3
"""Convert documents/presentations between formats.

Usage:
  python3 convert.py --input <path-or-url> --to pptx|docx|pdf|md \
      [--title "..."] [--subtitle "..."] [--image <path>]... [--min-slides 5] [--outdir DIR]

Prints a JSON manifest to stdout. Outputs default to
skills/doc-convert/state/output-history/YYYY-MM-DD/<run-id>/.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_io
from doc_io import DocConvertError

try:
    import google_io
except Exception:  # google libs optional; targets that need them fail with a clear message
    google_io = None

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# file targets + "direct to cloud" targets (gdoc/gslides create drafts in Google Workspace)
TARGETS = ("pptx", "docx", "pdf", "md", "gdoc", "gslides")


def new_run_dir(outdir: str | None) -> str:
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        return outdir
    now = datetime.datetime.now()
    run = os.path.join(SKILL_DIR, "state", "output-history",
                       now.strftime("%Y-%m-%d"), f"{now.strftime('%H%M%S')}-{secrets.token_hex(4)}")
    os.makedirs(run, exist_ok=True)
    return run


def build_docx(doc: dict, sections: list[dict], out_path: str) -> None:
    import docx
    from docx.shared import Pt, RGBColor

    d = docx.Document()
    h = d.add_heading(doc["title"], level=0)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    for sec in sections:
        if sec["title"]:
            d.add_heading(sec["title"], level=1)
        for item in sec["items"]:
            p = d.add_paragraph(item, style="List Bullet")
            for run in p.runs:
                run.font.size = Pt(11)
    d.save(out_path)


def to_pdf(src_path: str, run_dir: str) -> str:
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", run_dir, src_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    expected = os.path.join(run_dir, os.path.splitext(os.path.basename(src_path))[0] + ".pdf")
    if proc.returncode != 0 or not os.path.exists(expected):
        raise DocConvertError(f"LibreOffice PDF conversion failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    return expected


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert documents between formats")
    ap.add_argument("--input", required=True, help="Local file path or public URL / Google link")
    ap.add_argument("--to", required=True, choices=TARGETS)
    ap.add_argument("--title", default="", help="Override document title")
    ap.add_argument("--subtitle", default="", help="Subtitle for the pptx title slide")
    ap.add_argument("--image", action="append", default=[], help="Image file to place on slides (repeatable)")
    ap.add_argument("--min-slides", type=int, default=5)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    manifest: dict = {"success": False, "input": args.input, "target": args.to, "warnings": []}
    try:
        run_dir = new_run_dir(args.outdir)
        manifest["run_dir"] = run_dir

        src = args.input
        if doc_io.is_url(src):
            # Private Google file: use authorized API if a token exists; else public download.
            if google_io and google_io.is_google_url(src) and google_io.has_token():
                src = google_io.download_private(src, os.path.join(run_dir, "input"))
                manifest["downloaded_to"] = src
                manifest["source_access"] = "google-authorized"
            else:
                src = doc_io.download(src, os.path.join(run_dir, "input"))
                manifest["downloaded_to"] = src
        elif not os.path.exists(src):
            raise DocConvertError(f"Input file not found: {src}")
        else:
            # keep a copy so the run dir is self-contained and under the workspace
            copied = os.path.join(run_dir, "input", os.path.basename(src))
            os.makedirs(os.path.dirname(copied), exist_ok=True)
            shutil.copy2(src, copied)
            src = copied

        src_ext = doc_io.detect_ext(src)
        manifest["detected_type"] = src_ext
        if src_ext == "." + args.to:
            manifest["warnings"].append("input and target formats are the same")

        base = os.path.splitext(os.path.basename(src))[0]

        # Fast path: office file -> pdf keeps original layout via LibreOffice.
        if args.to == "pdf" and src_ext in (".docx", ".pptx"):
            out_path = to_pdf(src, run_dir)
            manifest.update({"success": True, "output": out_path})
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return 0

        doc = doc_io.extract(src)
        if args.title:
            doc["title"] = args.title
        sections = doc_io.outline_sections(doc)
        manifest["sections"] = len(sections)

        if args.to in ("gdoc", "gslides"):
            # "Direct to cloud": create a draft in Google Workspace, return its URL.
            if not google_io:
                raise DocConvertError("Thiếu Google API libs. Cài: pip3 install google-api-python-client google-auth-oauthlib")
            if not google_io.has_token():
                raise DocConvertError(
                    "Chưa authorize Google. Chạy 1 lần: python3 skills/doc-convert/scripts/authorize_google.py")
            if args.to == "gdoc":
                res = google_io.create_google_doc(doc["title"], doc)
            else:
                res = google_io.create_google_slides(doc["title"], sections)
            manifest.update({"success": True, "google_url": res["url"], "google_id": res["id"],
                             "title": doc["title"]})
            manifest.update({k: v for k, v in res.items() if k == "slides"})
            with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, ensure_ascii=False, indent=2)
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            return 0
        elif args.to == "md":
            out_path = os.path.join(run_dir, base + ".md")
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(doc_io.to_markdown(doc))
        elif args.to == "docx":
            out_path = os.path.join(run_dir, base + ".docx")
            build_docx(doc, sections, out_path)
        elif args.to == "pptx":
            import build_pptx
            out_path = os.path.join(run_dir, base + ".pptx")
            stats = build_pptx.build(doc, sections, out_path, min_slides=args.min_slides,
                                     images=args.image, subtitle=args.subtitle)
            manifest.update(stats)
        else:  # pdf from text-ish input: build docx first, then convert
            tmp_docx = os.path.join(run_dir, base + ".docx")
            build_docx(doc, sections, tmp_docx)
            out_path = to_pdf(tmp_docx, run_dir)

        manifest.update({"success": True, "output": out_path, "title": doc["title"]})
    except DocConvertError as err:
        manifest["error"] = str(err)
    except Exception as err:  # unexpected - keep JSON contract for the agent
        manifest["error"] = f"{type(err).__name__}: {err}"

    with open(os.path.join(manifest.get("run_dir", "."), "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
