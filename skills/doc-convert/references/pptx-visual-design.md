# PPTX visual design (build_pptx.py)

How the deck builder produces branded, content-aware slides, plus the python-pptx and
validate_output.py pitfalls discovered while extending it. Read before editing `build_pptx.py`.

## What build_pptx emits

- Cover + closing slide: full-bleed navy (`BRAND_BG`) background, white title, white accent bar.
- Section dividers: full-bleed section colour — green `OPPORTUNITY`, red `RISK`, navy `ACCENT` — with a white top-aligned title (NOT vertically centred; that was a bug).
- Content slides: section-coloured title + accent bar, bullets left, image right.
- Content-aware templates auto-picked inside `build()`:
  - **stat cards** — 2-4 bullets carrying unit-bearing figures -> full-width cards, key figure blown up in the section colour;
  - **card grid** — a watchlist/action-style title with short items -> 2-column card grid;
  - **full-bleed image divider** — a divider with a photo -> photo as background + translucent colour scrim;
  - otherwise **bullet + image**.

## Section colour phase (`_section_color`)

- Markers switch the phase: "cơ hội"/"opportunit" -> opportunity (green), "rủi ro"/"risk" -> risk (red).
- level-3 sub-headings inherit the current phase; level <= 2 headings reset to neutral, so trailing "Watchlist"/"Suggested actions" after "Risks" are not stained red.
- PITFALL: `_paginate()` re-chunks sections into new dicts and MUST copy the `level` field through, otherwise every sub-heading silently degrades to level 2 and the colour resets. `outline_sections` must likewise store `b.get("level", 2)`.

## Detection heuristics

- Stat figures: REQUIRE a unit. Regex = number `\d[\d.,]*` + unit `%|tỉ|triệu|nghìn|lần|ngày|giờ|tháng|năm|USD|$|x|×|...`. A bare number is NOT a stat — "Nghị định 142" and the "2" in "C2PA" must not be big-upped.
- Card grid: gate on BOTH a title marker ("chỉ báo"/"theo dõi"/"hành động"/"watch"/"action"/"suggest"/"recommend"/...) AND items <= ~160 chars. A length-only check over-fires on any generic short section (e.g. a "Mục tiêu" section with two bullets).

## python-pptx techniques that keep validate_output.py green

- Full-bleed scrim: a slide-covering rectangle is treated by the validator's overlap check as a "rule" (no text + has `<p:style>`), so it "crosses" every text shape. Strip `<p:style>` (`_strip_style_ref`) so it reads as inert furniture.
- object-fit: cover without canvas overflow: `add_picture(img, l, t, w, h)` then set `crop_left`/`crop_right` (or `crop_top`/`crop_bottom`) to centre-crop. Scaling a picture past the slide trips the validator's `bounds` check (negative left / width > canvas).
- Solid background: `slide.background.fill.solid()` + `fore_color.rgb = ...` (python-pptx 1.0.2+).
- Z-order: `_send_to_back(shape)` removes the element and re-inserts at spTree index 2 (behind all placeholders). To stack picture-behind-scrim-behind-placeholders, send the scrim to back FIRST, then the picture (last one sent to back ends up bottom-most).
- Translucent overlay: append `<a:alpha val="..."/>` inside `<a:srgbClr>`; val = opacity% x 1000 (e.g. 70 -> 70000).

## Known validator false positives / round-trip traps

- `prose` ("every paragraph is a bullet"): fires on legitimately bullet-only sources, e.g. a morning-report brief. Check whether the source actually had prose blocks before treating it as a defect — don't blindly "fix" a bullet-only report.
- `_extract_pptx` labels title-less slides "Slide N". A pre-fix (Blank-layout) deck round-trips into a docx full of "Slide N" headings; fixed decks carry real title placeholders so this no longer happens.
