"""Build a .pptx with a consistent layout from an extracted document outline."""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ACCENT = RGBColor(0x1F, 0x3A, 0x5F)   # dark blue
BODY = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x6B, 0x6B, 0x6B)
MAX_BULLETS_PER_SLIDE = 6
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def build(doc: dict, sections: list[dict], out_path: str, min_slides: int = 5,
          images: list[str | None] | None = None, subtitle: str = "",
          credits: list[dict] | None = None) -> dict:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    # Keep one slot per requested image, None where the fetch failed, so a missing
    # picture leaves its own slide bare instead of shifting every later picture onto
    # the wrong section.
    images = [p if p and os.path.exists(p) else None for p in (images or [])]
    img_iter = iter(images)

    _title_slide(prs, doc["title"], subtitle)
    content_sections = _paginate(sections)
    if len(content_sections) + 2 < min_slides:
        content_sections = _paginate(sections, max_bullets=3)
    agenda = [s["title"] for s in content_sections if s["title"]]
    if agenda:
        _bullet_slide(prs, "Agenda" if _is_english(doc) else "Nội dung", agenda[:8], None)
    for sec in content_sections:
        _bullet_slide(prs, sec["title"] or doc["title"], sec["items"], next(img_iter, None))
    if credits:
        _credits_slide(prs, credits, english=_is_english(doc))
    _closing_slide(prs, doc["title"])

    while len(prs.slides) < min_slides:
        _bullet_slide(prs, doc["title"], ["(bổ sung)"], None)

    prs.save(out_path)
    return {"slides": len(prs.slides), "images_used": sum(1 for p in images if p)}


def _paginate(sections: list[dict], max_bullets: int = MAX_BULLETS_PER_SLIDE) -> list[dict]:
    out: list[dict] = []
    for sec in sections:
        items = sec["items"] or [""]
        for i in range(0, len(items), max_bullets):
            chunk = [t for t in items[i:i + max_bullets] if t]
            title = sec["title"] if i == 0 else f"{sec['title']} (tiếp)"
            out.append({"title": title, "items": chunk})
    return out


def _is_english(doc: dict) -> bool:
    sample = (doc["title"] + " " + " ".join(b["text"] for b in doc["blocks"][:10])).lower()
    vi_chars = sum(1 for ch in sample if ch in "ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ")
    return vi_chars < 3


def _title_slide(prs: Presentation, title: str, subtitle: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _accent_bar(slide, top=Inches(3.4))
    box = slide.shapes.add_textbox(Inches(0.8), Inches(2.2), SLIDE_W - Inches(1.6), Inches(1.2))
    p = box.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = ACCENT
    if subtitle:
        sub = slide.shapes.add_textbox(Inches(0.8), Inches(3.7), SLIDE_W - Inches(1.6), Inches(0.8))
        sp = sub.text_frame.paragraphs[0]
        sp.text = subtitle
        sp.font.size = Pt(18)
        sp.font.color.rgb = MUTED


def _bullet_slide(prs: Presentation, title: str, bullets: list[str], image: str | None) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _accent_bar(slide, top=Inches(1.05))
    tbox = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), SLIDE_W - Inches(1.2), Inches(0.7))
    tp = tbox.text_frame.paragraphs[0]
    tp.text = title[:120]
    tp.font.size = Pt(28)
    tp.font.bold = True
    tp.font.color.rgb = ACCENT

    body_width = SLIDE_W - Inches(1.2) - (Inches(4.2) if image else Inches(0))
    body = slide.shapes.add_textbox(Inches(0.7), Inches(1.4), body_width, SLIDE_H - Inches(2.0))
    tf = body.text_frame
    tf.word_wrap = True
    for i, text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + text
        p.font.size = Pt(18)
        p.font.color.rgb = BODY
        p.space_after = Pt(10)
    if image:
        try:
            slide.shapes.add_picture(image, SLIDE_W - Inches(4.4), Inches(1.5), width=Inches(3.8))
        except Exception:
            pass  # bad image must not break the deck


def _credits_slide(prs: Presentation, credits: list[dict], english: bool) -> None:
    """CC-BY images must name the creator. cc0/pdm need not, but crediting all is simpler."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _accent_bar(slide, top=Inches(1.05))
    tbox = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), SLIDE_W - Inches(1.2), Inches(0.7))
    tp = tbox.text_frame.paragraphs[0]
    tp.text = "Image credits" if english else "Nguồn ảnh"
    tp.font.size = Pt(28)
    tp.font.bold = True
    tp.font.color.rgb = ACCENT

    body = slide.shapes.add_textbox(Inches(0.7), Inches(1.4), SLIDE_W - Inches(1.4), SLIDE_H - Inches(2.0))
    tf = body.text_frame
    tf.word_wrap = True
    for i, credit in enumerate(credits):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        title = (credit.get("title") or credit.get("query") or "Untitled")[:60]
        creator = credit.get("creator") or "Unknown"
        licence = credit.get("license") or "CC"
        p.text = f"•  {title} — {creator} ({licence}) · Openverse"
        p.font.size = Pt(13)
        p.font.color.rgb = MUTED
        p.space_after = Pt(6)


def _closing_slide(prs: Presentation, title: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _accent_bar(slide, top=Inches(3.4))
    box = slide.shapes.add_textbox(Inches(0.8), Inches(2.6), SLIDE_W - Inches(1.6), Inches(1.0))
    p = box.text_frame.paragraphs[0]
    p.text = "Tóm tắt & Q&A"
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.color.rgb = ACCENT
    sub = slide.shapes.add_textbox(Inches(0.8), Inches(3.7), SLIDE_W - Inches(1.6), Inches(0.6))
    sp = sub.text_frame.paragraphs[0]
    sp.text = title
    sp.font.size = Pt(16)
    sp.font.color.rgb = MUTED


def _accent_bar(slide, top) -> None:
    from pptx.enum.shapes import MSO_SHAPE

    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), top, SLIDE_W, Pt(4))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
