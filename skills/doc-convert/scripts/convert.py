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
import image_search
from doc_io import DocConvertError

try:
    import google_io
except Exception:  # google libs optional; targets that need them fail with a clear message
    google_io = None

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# file targets + "direct to cloud" targets (gdoc/gslides create drafts in Google Workspace)
TARGETS = ("pptx", "docx", "pdf", "md", "gdoc", "gslides")

# python-docx's default template leaves body text on the theme's minor font, which is
# Cambria. Cambria ships with Office but not with Linux, so the `pdf` target -- which
# renders through headless LibreOffice -- substituted a serif face that has no
# precomposed Vietnamese glyphs. Diacritics were then drawn as separate combining
# glyphs with their own advance width: "so voi" rendered as "so vo i" with the tone
# mark beside the letter instead of above it.
#
# Calibri is the safe pin: Word and PowerPoint have it, and LibreOffice maps it to the
# metric-compatible Carlito, which does carry precomposed Vietnamese (U+1EA1 etc.).
# The pptx target already renders correctly because its theme pins both the major and
# the minor font to Calibri.
DOCX_FONT = "Calibri"
# python-docx's numbering.xml draws bullets as U+F0B7 -- a private-use codepoint that
# only exists in the Symbol font. Linux maps Symbol to OpenSymbol, which has nothing at
# F0B7, so every bullet rendered as a tofu box. U+2022 is the real BULLET codepoint and
# lives in the body font.
SYMBOL_BULLET = "\uf0b7"   # private-use codepoint, Symbol font only
UNICODE_BULLET = "\u2022"  # BULLET, present in Calibri/Carlito


def new_run_dir(outdir: str | None) -> str:
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        return outdir
    now = datetime.datetime.now()
    run = os.path.join(SKILL_DIR, "state", "output-history",
                       now.strftime("%Y-%m-%d"), f"{now.strftime('%H%M%S')}-{secrets.token_hex(4)}")
    os.makedirs(run, exist_ok=True)
    return run


def _pin_font(style, name: str) -> None:
    """Pin a style to a literal font, overriding the template's theme reference.

    Setting only ``style.font.name`` leaves the ``w:asciiTheme``/``w:hAnsiTheme``
    attributes in place, and both Word and LibreOffice prefer the theme reference
    over the literal one. The theme attributes have to go.
    """
    from docx.oxml.ns import qn

    style.font.name = name
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
        rfonts.set(qn("w:" + attr), name)
    for attr in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
        theme_attr = qn("w:" + attr)
        if theme_attr in rfonts.attrib:
            del rfonts.attrib[theme_attr]


def _fix_bullet_glyph(document, name: str) -> None:
    """Swap the Symbol-font private-use bullet for a real U+2022 in the body font."""
    from docx.oxml.ns import qn

    try:
        numbering = document.part.numbering_part.element
    except (AttributeError, KeyError, NotImplementedError):
        return
    for lvl_text in numbering.iter(qn("w:lvlText")):
        if lvl_text.get(qn("w:val")) == SYMBOL_BULLET:
            lvl_text.set(qn("w:val"), UNICODE_BULLET)
    for rfonts in numbering.iter(qn("w:rFonts")):
        if rfonts.get(qn("w:ascii")) == "Symbol":
            for attr in ("ascii", "hAnsi", "cs"):
                rfonts.set(qn("w:" + attr), name)


def build_docx(doc: dict, out_path: str) -> None:
    import docx
    from docx.shared import Pt, RGBColor

    d = docx.Document()
    for style_name in ("Normal", "Title", "Heading 1", "Heading 2", "Heading 3",
                       "Heading 4", "List Bullet"):
        try:
            _pin_font(d.styles[style_name], DOCX_FONT)
        except KeyError:
            pass
    _fix_bullet_glyph(d, DOCX_FONT)

    h = d.add_heading(doc["title"], level=0)
    for run in h.runs:
        run.font.name = DOCX_FONT
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

    # Walk the blocks rather than the slide outline. `outline_sections` flattens every
    # paragraph into sentence-sized `items` because that is what slides want; reusing it
    # here turned every line of prose into a bullet and split long paragraphs across
    # several of them, so the Word file held no body text at all.
    for block in doc["blocks"]:
        if block["kind"] == "heading":
            heading = d.add_heading(block["text"], level=min(block.get("level", 1), 4))
            for run in heading.runs:
                run.font.name = DOCX_FONT
            continue
        style = "List Bullet" if block["kind"] == "bullet" else None
        p = d.add_paragraph(block["text"], style=style) if style else d.add_paragraph(block["text"])
        for run in p.runs:
            run.font.name = DOCX_FONT
            run.font.size = Pt(11)
    d.save(out_path)


def resolve_images(args, doc: dict, sections: list[dict], run_dir: str,
                   manifest: dict, build_pptx) -> tuple[list, list]:
    """Decide which pictures the deck gets. Never returns an irrelevant one.

    Explicit --image wins. Otherwise we search Openverse, but only with English
    queries: the agent supplies --image-query per section, or the section titles
    themselves serve when the document is already English. A Vietnamese title is
    left unsearched -- Openverse answers it with fishing boats -- and the slide
    simply goes without a picture.
    """
    if args.image:
        return list(args.image), []
    if args.no_auto_images:
        return [], []

    queries = list(args.image_query or [])
    if not queries:
        if not build_pptx._is_english(doc):
            manifest["warnings"].append("image_search_needs_english_query")
            return [], []
        queries = [sec["title"] or doc["title"] for sec in sections]

    paths, credits, warnings = image_search.fetch(queries, os.path.join(run_dir, "images"))
    manifest["warnings"].extend(warnings)
    if credits:
        manifest["image_credits"] = credits
    return paths, credits


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
    ap.add_argument("--image-query", action="append", default=[],
                    help="English search phrase for one section's slide image, in section order "
                         "(repeatable). Openverse returns nothing useful for Vietnamese queries.")
    ap.add_argument("--no-auto-images", action="store_true",
                    help="Never search Openverse; leave slides without pictures.")
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
            build_docx(doc, out_path)
        elif args.to == "pptx":
            import build_pptx
            out_path = os.path.join(run_dir, base + ".pptx")
            images, credits = resolve_images(args, doc, sections, run_dir, manifest, build_pptx)
            stats = build_pptx.build(doc, sections, out_path, min_slides=args.min_slides,
                                     images=images, subtitle=args.subtitle, credits=credits)
            for name in stats.pop("images_rejected", []):
                manifest["warnings"].append(f"image_embed_failed:{name}")
            manifest.update(stats)
        else:  # pdf from text-ish input: build docx first, then convert
            tmp_docx = os.path.join(run_dir, base + ".docx")
            build_docx(doc, tmp_docx)
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
