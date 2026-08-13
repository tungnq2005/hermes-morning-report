#!/usr/bin/env python3
"""Check a converted file against renderer-independent invariants.

Rendering a .pptx through LibreOffice only proves what LibreOffice would draw. The
product is opened in PowerPoint, Word, Canva and Google Slides, so the checks here
avoid asking any one renderer's opinion:

  * geometry is read straight out of the OOXML (every renderer honours it);
  * text is measured with the real Calibri-metric font file, so the fit holds for
    PowerPoint's Calibri and LibreOffice's Carlito alike;
  * content is compared against the source document, which catches text that a
    converter dropped or mangled no matter how pretty the result looks.

Usage:
  python3 validate_output.py --file <out.pptx|out.docx|out.pdf> [--source <input>]

Prints a JSON report. Exit code 1 when a check fails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_io  # noqa: E402

# The deck pins Calibri. Carlito is its metric-compatible clone, so measuring with
# whichever is installed gives line breaks that match both renderers.
FONT_CANDIDATES = ("Calibri", "Carlito")
# Diacritics that separate real Vietnamese from mojibake or stripped accents.
VI_DIACRITICS = "ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ"
# Ignore text shorter than this when comparing coverage: slide furniture such as
# numbers and the "cont." suffix has no counterpart in the source.
MIN_COVERAGE_CHARS = 25
# Content reaching less than this fraction of the slide width means the layout is
# still sized for a narrower canvas than the deck actually uses.
CANVAS_USE_MIN = 0.82


def _font_path() -> str | None:
    if not shutil.which("fc-match"):
        return None
    for family in FONT_CANDIDATES:
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", family],
                                  capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:  # noqa: BLE001 - measurement is best-effort
            return None
        if path and os.path.basename(path).lower().startswith(tuple(f.lower() for f in FONT_CANDIDATES)):
            return path
    return None


def _measure(text: str, pt: float, font_path: str) -> tuple[int, int]:
    """Return (width, height) of one line in points, using the real font."""
    from PIL import ImageFont

    # Render at 4x for sub-point accuracy, then scale back.
    font = ImageFont.truetype(font_path, int(pt * 4))
    left, top, right, bottom = font.getbbox(text)
    return (right - left) / 4, (bottom - top) / 4


def _wrapped_lines(text: str, pt: float, width_pt: float, font_path: str) -> int:
    """Greedy word wrap with real metrics -- what both renderers do."""
    words = text.split()
    if not words:
        return 1
    lines, current = 1, ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _measure(candidate, pt, font_path)[0] <= width_pt or not current:
            current = candidate
        else:
            lines += 1
            current = word
    return lines


def check_pptx(path: str, font_path: str | None) -> list[dict]:
    from pptx import Presentation
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Inches

    problems: list[dict] = []
    prs = Presentation(path)
    canvas_w, canvas_h = prs.slide_width, prs.slide_height

    for index, slide in enumerate(prs.slides, 1):
        def fail(check: str, detail: str) -> None:
            problems.append({"slide": index, "check": check, "detail": detail})

        title = slide.shapes.title
        if title is None or not title.text_frame.text.strip():
            fail("title_placeholder", "slide has no title placeholder or it is empty")
        if slide.slide_layout.name == "Blank":
            fail("layout", "slide uses the Blank layout, so it carries no structure")

        rules, texts, right_edges = [], [], []
        for shape in slide.shapes:
            if shape.left is None or shape.width is None:
                continue
            # Slide numbers and other furniture sit against the right margin and would
            # mask a body that never leaves the old 4:3 box.
            if shape.width > Inches(2):
                right_edges.append(shape.left + shape.width)
            if shape.left < 0 or shape.top < 0:
                fail("bounds", f"{shape.name} starts off-canvas")
            if shape.left + shape.width > canvas_w or shape.top + shape.height > canvas_h:
                fail("bounds", f"{shape.name} overruns the canvas")
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append((shape.name, shape.top, shape.top + shape.height))
            elif shape._element.find(qn("p:style")) is not None:
                rules.append((shape.name, shape.top, shape.top + shape.height))

        # A 4:3 layout dropped onto a 16:9 canvas keeps its old 10" geometry and leaves
        # the right-hand strip empty on every slide. Nothing overflows, so only the
        # unused width gives it away.
        if right_edges and max(right_edges) < canvas_w * CANVAS_USE_MIN:
            fail("canvas_use",
                 f"content stops at {max(right_edges) / canvas_w:.0%} of the slide width")

        for rule_name, top, bottom in rules:
            for text_name, text_top, text_bottom in texts:
                if min(bottom, text_bottom) - max(top, text_top) > 0:
                    fail("overlap", f"{rule_name} crosses {text_name}")

        # The expensive part: does the text actually fit its box in *any* renderer?
        if font_path:
            for shape in slide.shapes:
                if not shape.has_text_frame or not shape.text_frame.text.strip():
                    continue
                width_pt = Emu(shape.width).pt
                used = 0.0
                for para in shape.text_frame.paragraphs:
                    if not para.text.strip():
                        continue
                    pt = (para.font.size or Emu(0)).pt if para.font.size else 18.0
                    lines = _wrapped_lines(para.text, pt, width_pt * 0.94, font_path)
                    used += lines * pt * 1.22 + (para.space_after.pt if para.space_after else 0)
                if used > Emu(shape.height).pt * 1.02:
                    fail("overflow",
                         f"{shape.name}: text needs ~{used:.0f}pt in a "
                         f"{Emu(shape.height).pt:.0f}pt box")
    return problems


def check_docx(path: str) -> list[dict]:
    import docx

    problems: list[dict] = []
    d = docx.Document(path)
    used = {p.style.name for p in d.paragraphs if p.text.strip()}
    if "List Bullet" in used and "Normal" not in used:
        problems.append({"check": "prose", "detail":
                         "every paragraph is a bullet -- the document has no body text"})
    if not any(name.startswith("Heading") or name == "Title" for name in used):
        problems.append({"check": "headings", "detail": "no headings, so navigation is flat"})
    for para in d.paragraphs:
        for run in para.runs:
            if run.font.name and run.font.name not in ("Calibri", "Carlito"):
                problems.append({"check": "font", "detail":
                                 f"unexpected font {run.font.name!r} on {para.text[:40]!r}"})
                break
    return problems


def check_pdf(path: str) -> list[dict]:
    from pypdf import PdfReader

    problems: list[dict] = []
    reader = PdfReader(path)
    if not reader.pages:
        return [{"check": "pages", "detail": "PDF has no pages"}]

    fonts: set[str] = set()
    for page in reader.pages:
        for ref in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
            base = str(ref.get_object().get("/BaseFont") or "")
            fonts.add(base)
            # A non-embedded font is named without the ABCDEF+ subset prefix.
            if "+" not in base:
                problems.append({"check": "font_embedding", "detail":
                                 f"{base} is not embedded; the viewer will substitute it"})
    if not fonts:
        problems.append({"check": "font_embedding", "detail": "no fonts found in the PDF"})

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if "�" in text:
        problems.append({"check": "encoding", "detail": "replacement characters in the text layer"})
    return problems


def check_coverage(out_text: str, source: str) -> list[dict]:
    """Every substantial line of the source must survive into the output."""
    doc = doc_io.extract(source)
    haystack = _normalise(out_text)
    missing = []
    for block in doc["blocks"]:
        text = block["text"].strip()
        if len(text) < MIN_COVERAGE_CHARS:
            continue
        # Slides split long paragraphs, so match on the opening clause.
        probe = _normalise(text)[:60]
        if probe and probe not in haystack:
            missing.append(text[:70])
    problems = [{"check": "coverage", "detail": f"missing from output: {t!r}"} for t in missing[:10]]
    if len(missing) > 10:
        problems.append({"check": "coverage", "detail": f"...and {len(missing) - 10} more"})
    return problems


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pptx":
        from pptx import Presentation
        return "\n".join(
            para.text
            for slide in Presentation(path).slides
            for shape in slide.shapes if shape.has_text_frame
            for para in shape.text_frame.paragraphs
        )
    if ext == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(path).paragraphs)
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return ""


def vietnamese_ratio(text: str) -> float:
    letters = [ch for ch in text.lower() if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch in VI_DIACRITICS) / len(letters)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a converted document")
    ap.add_argument("--file", required=True, action="append",
                    help="Output file to check (repeatable)")
    ap.add_argument("--source", help="Original input, enables the content-coverage check")
    args = ap.parse_args()

    font_path = _font_path()
    report = {"font_used_for_measurement": font_path, "files": [], "success": True}

    for path in args.file:
        ext = os.path.splitext(path)[1].lower()
        entry: dict = {"path": path, "type": ext, "problems": []}
        if not os.path.exists(path):
            entry["problems"].append({"check": "exists", "detail": "file not found"})
        elif ext == ".pptx":
            entry["problems"] += check_pptx(path, font_path)
        elif ext == ".docx":
            entry["problems"] += check_docx(path)
        elif ext == ".pdf":
            entry["problems"] += check_pdf(path)
        else:
            entry["problems"].append({"check": "type", "detail": f"unsupported: {ext}"})

        if os.path.exists(path) and ext in (".pptx", ".docx", ".pdf"):
            text = extract_text(path)
            entry["vietnamese_diacritic_ratio"] = round(vietnamese_ratio(text), 4)
            if args.source:
                entry["problems"] += check_coverage(text, args.source)

        entry["ok"] = not entry["problems"]
        report["success"] &= entry["ok"]
        report["files"].append(entry)

    if not font_path:
        report.setdefault("warnings", []).append(
            "Calibri/Carlito not found - text-fit checks were skipped")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
