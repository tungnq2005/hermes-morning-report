"""Unit tests for the doc-convert skill. Run from the workspace root:
    python3 -m unittest discover skills/doc-convert/tests
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)

import doc_io  # noqa: E402
import build_pptx  # noqa: E402
import google_io  # noqa: E402


def make_sample_docx(path: str) -> None:
    import docx

    d = docx.Document()
    d.add_heading("Kế hoạch dự án AI", level=0)
    d.add_heading("Mục tiêu", level=1)
    d.add_paragraph("Tự động hoá bản tin buổi sáng cho khách hàng.")
    d.add_paragraph("Chuyển đổi tài liệu đa định dạng.", style="List Bullet")
    d.add_heading("Phạm vi", level=1)
    d.add_paragraph("Giai đoạn một tập trung vào Telegram.", style="List Bullet")
    d.add_paragraph("Giai đoạn hai tích hợp Google Workspace.", style="List Bullet")
    d.add_heading("Tiến độ", level=1)
    d.add_paragraph("Hoàn thành trong hai tuần kể từ khi ký hợp đồng.")
    d.save(path)


def make_sample_pptx(path: str) -> None:
    from pptx import Presentation

    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = "Demo Deck"
    s1.placeholders[1].text = "Subtitle"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Points"
    s2.placeholders[1].text_frame.text = "First point"
    prs.save(path)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="docconv-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_docx_extract_structure(self):
        path = os.path.join(self.tmp, "sample.docx")
        make_sample_docx(path)
        doc = doc_io.extract(path)
        self.assertEqual(doc["title"], "Kế hoạch dự án AI")
        kinds = {b["kind"] for b in doc["blocks"]}
        self.assertIn("heading", kinds)
        self.assertIn("bullet", kinds)
        sections = doc_io.outline_sections(doc)
        self.assertGreaterEqual(len(sections), 3)

    def test_pptx_extract(self):
        path = os.path.join(self.tmp, "deck.pptx")
        make_sample_pptx(path)
        doc = doc_io.extract(path)
        self.assertEqual(doc["title"], "Demo Deck")
        texts = " ".join(b["text"] for b in doc["blocks"])
        self.assertIn("First point", texts)

    def test_markdown_roundtrip(self):
        md_path = os.path.join(self.tmp, "notes.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write("# Tiêu đề\n\n## Phần một\n\n- ý một\n- ý hai\n\nĐoạn văn.\n")
        doc = doc_io.extract(md_path)
        out = doc_io.to_markdown(doc)
        self.assertIn("## Phần một", out)
        self.assertIn("- ý một", out)

    def test_unsupported_ext(self):
        path = os.path.join(self.tmp, "x.xyz")
        with open(path, "w") as fh:
            fh.write("data")
        with self.assertRaises(doc_io.DocConvertError):
            doc_io.extract(path)

    def test_google_link_resolution(self):
        url, ext = doc_io.resolve_download_url("https://docs.google.com/document/d/abc123XYZ/edit")
        self.assertIn("export?format=docx", url)
        self.assertEqual(ext, ".docx")
        url, ext = doc_io.resolve_download_url("https://docs.google.com/presentation/d/p456/edit#slide=1")
        self.assertIn("/export/pptx", url)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="docconv-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pptx_min_slides(self):
        path = os.path.join(self.tmp, "sample.docx")
        make_sample_docx(path)
        doc = doc_io.extract(path)
        sections = doc_io.outline_sections(doc)
        out = os.path.join(self.tmp, "out.pptx")
        stats = build_pptx.build(doc, sections, out, min_slides=5)
        self.assertTrue(os.path.exists(out))
        self.assertGreaterEqual(stats["slides"], 5)

    def test_built_docx_pins_font_and_bullet_glyph(self):
        """Guard the two defects that broke Vietnamese in the docx and pdf targets.

        Body text used to inherit the theme's minor font (Cambria), which LibreOffice
        replaced with a serif face lacking precomposed Vietnamese, and bullets used the
        Symbol-only codepoint U+F0B7, which rendered as a tofu box.
        """
        import zipfile

        import convert

        src = os.path.join(self.tmp, "sample.docx")
        make_sample_docx(src)
        doc = doc_io.extract(src)
        out = os.path.join(self.tmp, "built.docx")
        convert.build_docx(doc, doc_io.outline_sections(doc), out)

        with zipfile.ZipFile(out) as z:
            styles = z.read("word/styles.xml").decode("utf-8")
            numbering = z.read("word/numbering.xml").decode("utf-8")

        for style_id in ("Normal", "ListBullet", "Heading1", "Title"):
            match = re.search(r'<w:style [^>]*w:styleId="%s".*?</w:style>' % style_id, styles, re.S)
            self.assertIsNotNone(match, f"style {style_id} missing")
            rfonts = re.search(r"<w:rFonts([^/>]*)/>", match.group(0))
            self.assertIsNotNone(rfonts, f"style {style_id} has no rFonts")
            self.assertIn('w:ascii="Calibri"', rfonts.group(1), f"style {style_id} not pinned")
            # a surviving theme reference would win over the literal font
            self.assertNotIn("Theme=", rfonts.group(1), f"style {style_id} still points at the theme")

        self.assertNotIn(convert.SYMBOL_BULLET, numbering, "Symbol-font bullet survived")
        self.assertIn(convert.UNICODE_BULLET, numbering, "U+2022 bullet missing")
        self.assertNotIn('w:ascii="Symbol"', numbering, "numbering still asks for the Symbol font")

    def test_convert_cli_docx_to_pptx(self):
        src = os.path.join(self.tmp, "sample.docx")
        make_sample_docx(src)
        outdir = os.path.join(self.tmp, "run")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "convert.py"),
             "--input", src, "--to", "pptx", "--outdir", outdir],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest = json.loads(proc.stdout)
        self.assertTrue(manifest["success"])
        self.assertTrue(os.path.exists(manifest["output"]))
        self.assertGreaterEqual(manifest["slides"], 5)

    def test_convert_cli_pptx_to_docx(self):
        src = os.path.join(self.tmp, "deck.pptx")
        make_sample_pptx(src)
        outdir = os.path.join(self.tmp, "run2")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "convert.py"),
             "--input", src, "--to", "docx", "--outdir", outdir],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest = json.loads(proc.stdout)
        self.assertTrue(manifest["success"])
        self.assertTrue(manifest["output"].endswith(".docx"))

    @unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
    def test_convert_cli_docx_to_pdf(self):
        src = os.path.join(self.tmp, "sample.docx")
        make_sample_docx(src)
        outdir = os.path.join(self.tmp, "run3")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "convert.py"),
             "--input", src, "--to", "pdf", "--outdir", outdir],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest = json.loads(proc.stdout)
        self.assertTrue(manifest["success"])
        self.assertTrue(manifest["output"].endswith(".pdf"))


class NarrateTests(unittest.TestCase):
    def test_narrate_script(self):
        tmp = tempfile.mkdtemp(prefix="docconv-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        src = os.path.join(tmp, "sample.docx")
        make_sample_docx(src)
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "narrate.py"),
             "--input", src, "--lang", "Vietnamese", "--outdir", os.path.join(tmp, "aud")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(result["script_path"]))
        self.assertIn("generate_audio.py", result["suggested_tts_command"])


class GoogleTests(unittest.TestCase):
    def test_url_detection_and_id(self):
        self.assertTrue(google_io.is_google_url("https://docs.google.com/document/d/ABC123def/edit"))
        self.assertTrue(google_io.is_google_url("https://docs.google.com/presentation/d/PID456/edit"))
        self.assertTrue(google_io.is_google_url("https://drive.google.com/file/d/DRV789/view"))
        self.assertFalse(google_io.is_google_url("https://example.com/x.docx"))
        self.assertEqual(google_io.extract_file_id(
            "https://docs.google.com/document/d/ABC123def/edit"), "ABC123def")
        self.assertEqual(google_io.extract_file_id(
            "https://drive.google.com/file/d/DRV789/view"), "DRV789")

    def test_has_token_false_in_empty_dir(self):
        tmp = tempfile.mkdtemp(prefix="gcreds-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.assertFalse(google_io.has_token(tmp))

    def test_load_credentials_without_token_raises(self):
        tmp = tempfile.mkdtemp(prefix="gcreds-")
        self.addCleanup(shutil.rmtree, tmp, True)
        with self.assertRaises(google_io.GoogleAuthError):
            google_io.load_credentials(tmp)

    def test_convert_cli_gdoc_without_token_fails_cleanly(self):
        # gdoc target must fail with an actionable message, not a crash, when unauthorized.
        tmp = tempfile.mkdtemp(prefix="docconv-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        src = os.path.join(tmp, "sample.docx")
        make_sample_docx(src)
        env = dict(os.environ)
        # Hermetic: point creds dir at an empty temp dir so we never touch real creds/API.
        env["DOC_CONVERT_GCREDS_DIR"] = os.path.join(tmp, "empty-creds")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "convert.py"),
             "--input", src, "--to", "gdoc", "--outdir", os.path.join(tmp, "run")],
            capture_output=True, text=True, env=env)
        manifest = json.loads(proc.stdout)
        self.assertFalse(manifest["success"])
        self.assertIn("authorize", manifest["error"].lower())


if __name__ == "__main__":
    unittest.main()
