# Convert Document

Use this prompt when the user sends a file or link and asks to convert it to another format (Google Slides, Google Docs, PowerPoint, Word, PDF, Markdown).

Results are produced in Google Workspace: `convert.py` builds the deck/document, imports it into Google Slides / Google Docs, and exports whatever file the user asked for from there. A python-pptx deck renders differently in PowerPoint for Mac; the Google copy looks the same on every OS, so the link is the primary deliverable.

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
2. Target format:
   - `gslides` — **default for "make slides" / "làm slide" / "chuyển thành PowerPoint"**. Deck in Google Slides + a PDF copy.
   - `gdoc` — **default for "make a document" / "chuyển thành Word"**. Google Doc + a PDF copy.
   - `pptx` / `docx` — only when the user explicitly wants an Office file to keep. Built in Google, then exported, so it opens the same on Mac and Windows.
   - `pdf` — a PDF only.
   - `md` — Markdown, the one target that never goes through Google.

   Confirm only when genuinely ambiguous. If the user insists on a `.pptx` file, still deliver the Slides link alongside it.
3. Optional: presentation title/subtitle if the user provides one.

## What Google Does

Every target except `md` is imported into the user's Drive and rendered by Google:

- the manifest carries `google_url` (the link to deliver), `google_id`, `render_engine: google`, and `output` (the exported file, a PDF for `gslides`/`gdoc`);
- files are created **private** in the user's own Drive. Do not change sharing.
- `--no-google` forces local rendering; use it only for offline debugging, never for a customer deliverable.

If `google.authorized_token` is false, `gslides`/`gdoc` fail with an actionable message (relay it), and `pptx`/`docx`/`pdf` fall back to local rendering with a `google_unauthorized:rendered_locally` warning. When you see that warning, tell the user the file was rendered locally and may look different on macOS, and offer to re-run once `authorize_google.py` has been run.

## Images For Slides (gslides / pptx targets)

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
  --to <gslides|gdoc|pptx|docx|pdf|md> \
  [--title "<title>"] [--subtitle "<subtitle>"] \
  [--image-query "digital economy" --image-query "artificial intelligence"] \
  [--image <path> --image <path>] [--no-auto-images] \
  [--min-slides 5] [--rebuild]
```

A `.pptx` sent to `--to gslides` (or a `.docx` to `--to gdoc`) is uploaded **as-is** — the user asked to put *their* file on Google. Pass `--rebuild` when they want it re-laid out with our layouts and imagery ("làm lại slide cho đẹp", "add pictures").

Parse the JSON output.

- On `"success": true`: `google_url` is the link to deliver and `output` is the absolute path of the exported file (inside the workspace). A missing `output` with a `google_export_failed:` warning means the deck was too big for Drive's 10MB export — deliver the link alone and say the PDF could not be exported.
- `google_check.status` is the readback of the deck Google actually holds: `pass`, `fail` (see `problems`), or `unchecked` (the probe itself failed — not a pass).
- `images_used` counts the pictures that landed on slides; `image_credits` lists their creators and licences.
- `warnings` may carry `image_search_needs_english_query`, `image_search_no_result:<q>`, `image_search_failed:<q>:<Error>`, `image_unsupported_format:<q>` (a hit was WebP or similar; the next candidate was tried), `image_download_failed:<q>:<Error>`, `image_embed_failed:<file>`, or `image_search_disabled`. None of these are fatal.
- `images_used` counts pictures that actually landed on a slide, not pictures fetched.
- On failure: relay the `error` message honestly. Common cases: private Google link (ask the user to enable link sharing or upload the file), scanned PDF (unsupported), unsupported extension.

## Verify Before Delivering

Rendering the result yourself only proves what your renderer would draw; the customer
opens the deck in Google Slides on a Mac. Two things have to hold: the deck Google
imported is intact, and the exported file is clean.

`convert.py` already runs the Slides readback for you — check `google_check.status` in
the manifest. Run the validator on the exported file, and re-run the readback yourself
when you want to re-check a deck after editing it:

```bash
python3 skills/doc-convert/scripts/validate_output.py \
  --file "<output-path>" [--google "<google_url>"] --source "<input-path>"
```

- `"success": true` — deliver.
- Otherwise each entry lists `problems` with a `check` and a `detail`. `overflow`,
  `overlap`, `bounds`, `canvas_use`, `title_placeholder`, `layout` and `empty_slide`
  are layout faults; `prose` means a Word file came out as one long bullet list;
  `coverage` means source text is missing from the output; `font_embedding` and
  `encoding` are PDF faults; `readback` means the Slides probe itself failed, which
  proves nothing either way.
- Fix the cause and rebuild. Never deliver a file whose validation failed without
  telling the user exactly which check failed.

`--source` is optional but worth passing: it is the only check that notices content the
converter silently dropped.

## Deliver

Send one short message naming what was converted, the Google link, and then the exported file as a Telegram attachment:

```text
Đã chuyển `bao-cao.docx` → Google Slides, 8 slide. Mở được trên Mac, Windows và điện thoại:
https://docs.google.com/presentation/d/<id>/edit

MEDIA:<absolute-output-path-from-manifest>
```

The link MUST be the `google_url` from the manifest, and each `MEDIA:` path the workspace path from the manifest — never a `/tmp` path, never an invented URL. One `MEDIA:` line per file. Include the slide count for slide targets. If the manifest has no `output`, send the link alone and say why (the warning tells you).

Target turnaround is 5-10 minutes from receiving the file. Do not send progress updates in between; only the summary + attachment, or the error.
