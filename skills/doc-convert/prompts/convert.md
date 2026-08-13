# Convert Document

Use this prompt when the user sends a file or link and asks to convert it to another format (PowerPoint, Word, PDF, Markdown).

## Read First

- `skills/doc-convert/SKILL.md` guardrails

Run readiness check before claiming capability:

```bash
python3 skills/doc-convert/scripts/preflight.py --compact
```

If `environment_ok` is false, explain what is missing and stop.

## Determine Inputs

1. Input file: the Telegram-uploaded file's local path, a local path the user names, or a URL / Google Docs / Google Slides / Google Drive link.
   - **Private Google files** are supported when `preflight` shows `google.authorized_token: true`. The converter automatically uses the authorized Google API for `docs.google.com` / `drive.google.com` links; no need to make them public. If not authorized, only public links work.
2. Target format: `pptx`, `docx`, `pdf`, `md`, or **direct-to-cloud** `gdoc` (new Google Doc) / `gslides` (new Google Slides). If the user is vague ("make slides" → pptx, "make a document" → docx, "put it in Google Docs/Slides" → gdoc/gslides), confirm only when genuinely ambiguous.
3. Optional: presentation title/subtitle if the user provides one.

## Direct-to-cloud (gdoc / gslides)

For `--to gdoc` or `--to gslides` the converter creates a NEW file in the user's Google Drive and returns its URL in the manifest as `google_url`. Requires `google.authorized_token: true`. Deliver the `google_url` to the user as a clickable link (do NOT send a `MEDIA:` directive — there is no local file). If unauthorized, the command fails with an actionable message; relay it.

## Images For Slides (pptx target only)

The acceptance bar for generated PowerPoints is ≥5 slides, consistent layout, and relevant imagery. The converter fetches the pictures itself from Openverse (openly licensed, no API key) and appends a credits slide. Your job is to give it good queries.

Pass **one `--image-query` per section, in section order**, and write each query **in English** — Openverse indexes almost nothing under Vietnamese, and answers "Hạ tầng điện toán đám mây" with zero results. Translate the section title into a short, concrete English phrase:

| Section title | `--image-query` |
| --- | --- |
| Tổng quan kinh tế số | `digital economy` |
| Trí tuệ nhân tạo và dữ liệu lớn | `artificial intelligence` |
| Hạ tầng điện toán đám mây | `cloud data center` |

Rules:

- One query per section. If a section has no sensible picture, pass an empty string `--image-query ""` to leave that slide bare.
- A query that finds nothing leaves its own slide without a picture; the other slides keep theirs.
- Never pass `--image-query` in Vietnamese. A wrong picture is worse than no picture.
- `--image <path>` still overrides everything when the user supplies their own files.
- `--no-auto-images` disables the search entirely.

If the deck comes back with `images_used: 0` and a `image_search_no_result:*` warning, tell the user the deck was generated without imagery and offer to retry with different queries.

## Run

```bash
python3 skills/doc-convert/scripts/convert.py \
  --input "<path-or-url>" \
  --to <pptx|docx|pdf|md> \
  [--title "<title>"] [--subtitle "<subtitle>"] \
  [--image-query "digital economy" --image-query "artificial intelligence"] \
  [--image <path> --image <path>] [--no-auto-images] \
  [--min-slides 5]
```

Parse the JSON output.

- On `"success": true`: the `output` field is the absolute result path (inside the workspace).
- `images_used` counts the pictures that landed on slides; `image_credits` lists their creators and licences.
- `warnings` may carry `image_search_needs_english_query`, `image_search_no_result:<q>`, `image_search_failed:<q>:<Error>`, `image_unsupported_format:<q>` (a hit was WebP or similar; the next candidate was tried), `image_download_failed:<q>:<Error>`, `image_embed_failed:<file>`, or `image_search_disabled`. None of these are fatal.
- `images_used` counts pictures that actually landed on a slide, not pictures fetched.
- On failure: relay the `error` message honestly. Common cases: private Google link (ask the user to enable link sharing or upload the file), scanned PDF (unsupported), unsupported extension.

## Verify Before Delivering

Rendering the result yourself only proves what your renderer would draw; the customer
opens the file in PowerPoint, Word, Canva or Google Slides. Run the validator on every
produced file instead — it reads geometry out of the OOXML and measures text with the
real Calibri-metric font, so its verdict does not depend on LibreOffice:

```bash
python3 skills/doc-convert/scripts/validate_output.py \
  --file "<output-path>" [--file "<other-output>"] --source "<input-path>"
```

- `"success": true` — deliver.
- Otherwise each entry lists `problems` with a `check` and a `detail`. `overflow`,
  `overlap`, `bounds`, `canvas_use`, `title_placeholder` and `layout` are layout faults;
  `prose` means a Word file came out as one long bullet list; `coverage` means source
  text is missing from the output; `font_embedding` and `encoding` are PDF faults.
- Fix the cause and rebuild. Never deliver a file whose validation failed without
  telling the user exactly which check failed.

`--source` is optional but worth passing: it is the only check that notices content the
converter silently dropped.

## Deliver

Send the result as a Telegram attachment with a standalone directive line:

```text
MEDIA:<absolute-output-path-from-manifest>
```

One `MEDIA:` line per file. The path MUST be the workspace path from the manifest — never a `/tmp` path. Before the attachment, send one short message stating what was converted (e.g. "Đã chuyển `bao-cao.docx` → PowerPoint, 8 slides.") including the slide count for pptx targets.

Target turnaround is 5-10 minutes from receiving the file. Do not send progress updates in between; only the summary + attachment, or the error.
