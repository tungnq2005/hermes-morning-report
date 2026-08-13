"""Build a .pptx with a consistent layout from an extracted document outline.

Text goes into the layout's own placeholders rather than free-floating textboxes.
Hand-placed boxes rendered fine but carried no structure: every slide came out on the
Blank layout with no title placeholder, so PowerPoint's outline view was empty, a
theme change moved nothing, and importers like Canva saw loose boxes instead of a
title and a body. Placeholders also bring real bullet formatting and autofit.
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

ACCENT = RGBColor(0x1F, 0x3A, 0x5F)   # dark blue
BODY = RGBColor(0x33, 0x33, 0x33)
MUTED = RGBColor(0x6B, 0x6B, 0x6B)
MAX_BULLETS_PER_SLIDE = 6
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# python-pptx's default template is a 10x7.5 (4:3) deck. Widening slide_width to 16:9
# does not move the layouts' placeholders, so every slide used to render its content
# inside the old 4:3 box: a 9"-wide title centred at the 5" mark, a 4.42" body column
# that wrapped short sentences into three cramped lines, and 3.8" of dead space down
# the right-hand edge. Every placeholder is therefore re-fitted to the real canvas.
MARGIN = Inches(0.7)
GUTTER = Inches(0.5)
TITLE_TOP = Inches(0.4)
TITLE_H = Inches(1.0)
BODY_TOP = Inches(1.6)
BODY_H = SLIDE_H - BODY_TOP - Inches(0.8)
FULL_W = SLIDE_W - 2 * MARGIN
TEXT_W_WITH_IMAGE = Inches(6.9)
PIC_LEFT = MARGIN + TEXT_W_WITH_IMAGE + GUTTER
PIC_W = SLIDE_W - PIC_LEFT - MARGIN

# Indices into the default template's layout list.
LAYOUT_TITLE = 0        # Title Slide      -- title + subtitle placeholders
LAYOUT_TITLE_BODY = 1   # Title and Content
LAYOUT_TWO_CONTENT = 3  # Two Content      -- body on the left, picture on the right
LAYOUT_SECTION = 2      # Section Header

# Body text is sized to fit before it is written. A bare <a:normAutofit/> is a weak
# guarantee: PowerPoint only recomputes its shrink factor when the text box is edited,
# so a deck that overflows opens overflowing however the tag is set. The sizes below
# are tried largest-first and the first one whose estimated block height fits wins;
# normAutofit stays on only as a backstop for renderers that disagree with the estimate.
BODY_SIZE_CHOICES = (Pt(18), Pt(16), Pt(14), Pt(12), Pt(11))
# Calibri/Carlito average out near half the point size per character at body weights.
AVG_CHAR_WIDTH_EM = 0.50
LINE_HEIGHT_EM = 1.22
# A title long enough to wrap costs a slide most of its body room.
TITLE_SIZES = ((70, Pt(22)), (45, Pt(25)), (0, Pt(28)))
# Below this, a heading's whole body is a lead-in sentence rather than content.
DIVIDER_MAX_CHARS = 180

STRINGS = {
    "en": {"agenda": "Agenda", "credits": "Image credits",
           "closing": "Summary & Q&A", "continued": "cont."},
    "vi": {"agenda": "Nội dung", "credits": "Nguồn ảnh",
           "closing": "Tóm tắt & Q&A", "continued": "tiếp"},
}


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
    words = STRINGS["en" if _is_english(doc) else "vi"]

    _title_slide(prs, doc["title"], subtitle)
    # Reach min_slides by spreading the real content thinner, never by padding: the
    # deck used to append slides whose only bullet was the literal string "(bổ sung)",
    # and they landed after the closing slide.
    content_sections = _paginate(sections, words)
    for max_bullets in (3, 2, 1):
        if len(content_sections) + 2 >= min_slides:
            break
        content_sections = _paginate(sections, words, max_bullets=max_bullets)
    agenda = [s["title"] for s in content_sections if s["title"] and s["first"]]
    if agenda:
        _bullet_slide(prs, words["agenda"], agenda[:8], None)

    # Index the pictures by source section rather than walking them slide by slide: a
    # section long enough to be split across slides would otherwise eat its
    # neighbours' pictures and push every later one onto the wrong section.
    placed = 0
    rejected: list[str] = []
    for sec in content_sections:
        image = images[sec["src"]] if sec["first"] and sec["src"] < len(images) else None
        title = sec["title"] or doc["title"]
        # A heading whose whole body is one short line is a part divider, not a content
        # slide. Rendering it as one leaves a single bullet marooned in white space.
        if _is_divider(sec):
            embedded = _divider_slide(prs, title, sec["items"][0] if sec["items"] else "", image)
        else:
            embedded = _bullet_slide(prs, title, sec["items"], image)
        if image:
            if embedded:
                placed += 1
            else:
                rejected.append(os.path.basename(image))
    if credits:
        _credits_slide(prs, credits, words)
    _closing_slide(prs, doc["title"], words)
    _add_slide_numbers(prs)

    prs.save(out_path)
    return {"slides": len(prs.slides), "images_used": placed, "images_rejected": rejected}


def _paginate(sections: list[dict], words: dict,
              max_bullets: int = MAX_BULLETS_PER_SLIDE) -> list[dict]:
    """Split over-long sections across slides. Each chunk remembers which section it
    came from (`src`) and whether it opens it (`first`) so pictures stay aligned."""
    out: list[dict] = []
    for src, sec in enumerate(sections):
        items = sec["items"] or [""]
        for i in range(0, len(items), max_bullets):
            chunk = [t for t in items[i:i + max_bullets] if t]
            title = sec["title"] if i == 0 else f"{sec['title']} ({words['continued']})"
            out.append({"title": title, "items": chunk, "src": src, "first": i == 0})
    return out


def _is_english(doc: dict) -> bool:
    sample = (doc["title"] + " " + " ".join(b["text"] for b in doc["blocks"][:10])).lower()
    vi_chars = sum(1 for ch in sample if ch in "ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ")
    return vi_chars < 3


def _fit(shape, left, top, width, height) -> None:
    shape.left, shape.top, shape.width, shape.height = left, top, width, height


def _pick(sizes, measure: int):
    for threshold, size in sizes:
        if measure > threshold:
            return size
    return sizes[-1][1]


def estimated_text_height(bullets: list[str], size, width, space_after=Pt(10)):
    """Rough height of a bulleted block. Deliberately renderer-independent: it must
    hold for PowerPoint (Calibri) and LibreOffice (Carlito), whose metrics match."""
    if not bullets:
        return 0
    char_width = size * AVG_CHAR_WIDTH_EM
    # The placeholder's hanging indent costs roughly two characters of usable width.
    usable = max(width - Emu(int(char_width * 2)), Emu(1))
    per_line = max(int(usable / char_width), 1)
    lines = sum(max(-(-len(text) // per_line), 1) for text in bullets)
    return int(lines * size * LINE_HEIGHT_EM + len(bullets) * space_after)


def _fitting_body_size(bullets: list[str], width, height):
    for size in BODY_SIZE_CHOICES:
        if estimated_text_height(bullets, size, width) <= height:
            return size
    return BODY_SIZE_CHOICES[-1]


def _clear_effect_ref(shape) -> None:
    from pptx.oxml.ns import qn

    style = shape._element.find(qn("p:style"))
    if style is None:
        return
    effect_ref = style.find(qn("a:effectRef"))
    if effect_ref is not None:
        effect_ref.set("idx", "0")


def _style_title(placeholder, size=None) -> None:
    """Report titles read left-aligned. The 4:3 master centres them, which on a 16:9
    canvas parks the title off-centre over the dead right-hand strip. The Section
    Header master also upper-cases its title, which mangles Vietnamese diacritics and
    matches no other slide in the deck."""
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

    frame = placeholder.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    chosen = size or _pick(TITLE_SIZES, len(placeholder.text))
    for para in frame.paragraphs:
        para.alignment = PP_ALIGN.LEFT
        para.font.size = chosen
        para.font.bold = True
        para.font.color.rgb = ACCENT
        para.font._rPr.set("cap", "none")
        for run in para.runs:
            run.font._rPr.set("cap", "none")


def _title_slide(prs: Presentation, title: str, subtitle: str) -> None:
    from pptx.enum.text import PP_ALIGN

    slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_TITLE])
    slide.shapes.title.text = title
    # The title box is bottom-anchored, so its text sits against the lower edge: the
    # rule has to clear that edge or it strikes through the descenders.
    _fit(slide.shapes.title, MARGIN, Inches(2.1), FULL_W, Inches(1.4))
    _style_title(slide.shapes.title, size=Pt(40))
    sub = slide.placeholders[1]
    if subtitle:
        sub.text = subtitle
        _fit(sub, MARGIN, Inches(3.8), FULL_W, Inches(0.9))
        for para in sub.text_frame.paragraphs:
            para.alignment = PP_ALIGN.LEFT
            para.font.size = Pt(18)
            para.font.color.rgb = MUTED
    else:
        # An empty placeholder still prints its "Click to add subtitle" prompt in
        # some viewers; drop the shape when there is nothing to say.
        sub._element.getparent().remove(sub._element)
    _accent_bar(slide, top=Inches(3.62))


def _is_divider(sec: dict) -> bool:
    """One short line under a heading reads as a lead-in to a part, not as content."""
    if not sec["first"] or not sec["title"]:
        return False
    body = [item for item in sec["items"] if item.strip()]
    return len(body) <= 1 and sum(len(item) for item in body) <= DIVIDER_MAX_CHARS


def _divider_slide(prs: Presentation, title: str, lead: str, image: str | None) -> bool:
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

    slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_SECTION])
    text_w = TEXT_W_WITH_IMAGE if image else FULL_W
    slide.shapes.title.text = title
    _fit(slide.shapes.title, MARGIN, Inches(2.7), text_w, Inches(1.4))
    _style_title(slide.shapes.title, size=_pick(TITLE_SIZES, len(title)))
    slide.shapes.title.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM

    body = slide.placeholders[1]
    _fit(body, MARGIN, Inches(4.3), text_w, Inches(1.1))
    if lead:
        body.text = lead
        frame = body.text_frame
        frame.word_wrap = True
        for para in frame.paragraphs:
            para.alignment = PP_ALIGN.LEFT
            para.font.size = Pt(16)
            para.font.color.rgb = MUTED
    else:
        body._element.getparent().remove(body._element)
    _accent_bar(slide, top=Inches(4.15), width=text_w)

    if not image:
        return False
    try:
        _place_picture(slide, image, PIC_LEFT, BODY_TOP, PIC_W, BODY_H)
        return True
    except Exception:
        return False


def _bullet_slide(prs: Presentation, title: str, bullets: list[str],
                  image: str | None = None) -> bool:
    """Returns whether the picture actually landed -- a format python-pptx refuses
    must not be counted as imagery the deck carries."""
    from pptx.enum.text import MSO_ANCHOR

    layout = LAYOUT_TWO_CONTENT if image else LAYOUT_TITLE_BODY
    slide = prs.slides.add_slide(prs.slide_layouts[layout])
    slide.shapes.title.text = title
    _fit(slide.shapes.title, MARGIN, TITLE_TOP, FULL_W, TITLE_H)
    _style_title(slide.shapes.title)
    # A rule under the title gives every content slide the same visual anchor.
    _accent_bar(slide, top=TITLE_TOP + TITLE_H + Inches(0.06), height=Pt(2))

    body = slide.placeholders[1]
    _fit(body, MARGIN, BODY_TOP, TEXT_W_WITH_IMAGE if image else FULL_W, BODY_H)
    frame = body.text_frame
    frame.word_wrap = True
    # A slide carrying one short line looks abandoned pinned to the top edge.
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE if len(bullets) <= 2 else MSO_ANCHOR.TOP
    # Let PowerPoint shrink the text if it still overflows the placeholder.
    _enable_shrink_on_overflow(frame)
    size = _fitting_body_size(bullets, body.width, body.height)
    for i, text in enumerate(bullets):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.text = text
        para.level = 0
        para.font.size = size
        para.font.color.rgb = BODY
        para.space_after = Pt(10)

    if not image:
        return False
    # The picture placeholder only reserves the space; a real picture shape replaces it
    # so the image can be scaled to its own aspect ratio instead of being stretched.
    picture_ph = slide.placeholders[2]
    picture_ph._element.getparent().remove(picture_ph._element)
    try:
        _place_picture(slide, image, PIC_LEFT, BODY_TOP, PIC_W, BODY_H)
        return True
    except Exception:
        return False  # bad image must not break the deck; the caller reports it


def _place_picture(slide, image: str, left, top, width, height) -> None:
    """Fit the picture inside the placeholder's box without distorting it."""
    picture = slide.shapes.add_picture(image, left, top)
    scale = min(width / picture.width, height / picture.height)
    picture.width = Emu(int(picture.width * scale))
    picture.height = Emu(int(picture.height * scale))
    picture.left = Emu(int(left + (width - picture.width) / 2))
    picture.top = Emu(int(top + (height - picture.height) / 2))


def _enable_shrink_on_overflow(frame) -> None:
    """python-pptx has no setter for the placeholder's shrink-text-on-overflow, and
    PowerPoint needs the element present to apply it."""
    from pptx.oxml.ns import qn

    body_pr = frame._txBody.find(qn("a:bodyPr"))
    if body_pr is None:
        return
    for tag in ("a:normAutofit", "a:spAutoFit", "a:noAutofit"):
        existing = body_pr.find(qn(tag))
        if existing is not None:
            body_pr.remove(existing)
    body_pr.append(body_pr.makeelement(qn("a:normAutofit"), {}))


def _credits_slide(prs: Presentation, credits: list[dict], words: dict) -> None:
    """CC-BY images must name the creator. cc0/pdm need not, but crediting all is simpler."""
    lines = []
    for credit in credits:
        title = (credit.get("title") or credit.get("query") or "Untitled")[:60]
        creator = credit.get("creator") or "Unknown"
        licence = credit.get("license") or "CC"
        lines.append(f"{title} — {creator} ({licence}) · Openverse")

    slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_TITLE_BODY])
    slide.shapes.title.text = words["credits"]
    _fit(slide.shapes.title, MARGIN, TITLE_TOP, FULL_W, TITLE_H)
    _style_title(slide.shapes.title)
    _accent_bar(slide, top=TITLE_TOP + TITLE_H + Inches(0.06), height=Pt(2))
    body = slide.placeholders[1]
    _fit(body, MARGIN, BODY_TOP, FULL_W, BODY_H)
    frame = body.text_frame
    frame.word_wrap = True
    _enable_shrink_on_overflow(frame)
    for i, line in enumerate(lines):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.text = line
        para.font.size = Pt(13)
        para.font.color.rgb = MUTED
        para.space_after = Pt(6)


def _closing_slide(prs: Presentation, title: str, words: dict) -> None:
    """The Section Header layout stacks its title *below* the text placeholder, which
    reads as a stray caption above the heading until both are placed explicitly."""
    from pptx.enum.text import PP_ALIGN

    slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_SECTION])
    slide.shapes.title.text = words["closing"]
    _fit(slide.shapes.title, MARGIN, Inches(2.5), FULL_W, Inches(0.9))
    _style_title(slide.shapes.title, size=Pt(32))
    body = slide.placeholders[1]
    body.text = title
    _fit(body, MARGIN, Inches(3.8), FULL_W, Inches(0.8))
    for para in body.text_frame.paragraphs:
        para.alignment = PP_ALIGN.LEFT
        para.font.size = Pt(16)
        para.font.color.rgb = MUTED
    _accent_bar(slide, top=Inches(3.62))


def _accent_bar(slide, top, left=None, width=None, height=Pt(4), color=ACCENT) -> None:
    from pptx.enum.shapes import MSO_SHAPE

    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        MARGIN if left is None else left,
        top,
        FULL_W if width is None else width,
        height,
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    # An empty <a:effectLst/> is not enough on its own: the shape style still points at
    # the theme's effect #2, and LibreOffice honours that reference, drawing a drop
    # shadow under what should be a flat rule. Point the reference at "no effect".
    bar.shadow.inherit = False
    _clear_effect_ref(bar)


def _add_slide_numbers(prs: Presentation) -> None:
    """A report deck is referred to by slide number; the title slide keeps none."""
    for index, slide in enumerate(prs.slides, 1):
        if index == 1:
            continue
        box = slide.shapes.add_textbox(SLIDE_W - Inches(1.1), SLIDE_H - Inches(0.6),
                                       Inches(0.7), Inches(0.35))
        para = box.text_frame.paragraphs[0]
        para.text = str(index)
        para.font.size = Pt(11)
        para.font.color.rgb = MUTED
