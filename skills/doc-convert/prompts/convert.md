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

The acceptance bar for generated PowerPoints is ≥5 slides, consistent layout, and relevant imagery. Before running the converter for a pptx target:

1. Pick 2-4 short image search queries from the document's main topics.
2. Use the available web/image tools to find and download 2-4 relevant, license-safe images into the run's directory or any workspace path.
3. Pass each downloaded file with a repeated `--image <path>` flag.

If image search is unavailable or fails, continue without images and tell the user the deck was generated without imagery this time.

## Run

```bash
python3 skills/doc-convert/scripts/convert.py \
  --input "<path-or-url>" \
  --to <pptx|docx|pdf|md> \
  [--title "<title>"] [--subtitle "<subtitle>"] \
  [--image <path> --image <path>] \
  [--min-slides 5]
```

Parse the JSON output.

- On `"success": true`: the `output` field is the absolute result path (inside the workspace).
- On failure: relay the `error` message honestly. Common cases: private Google link (ask the user to enable link sharing or upload the file), scanned PDF (unsupported), unsupported extension.

## Deliver

Send the result as a Telegram attachment with a standalone directive line:

```text
MEDIA:<absolute-output-path-from-manifest>
```

One `MEDIA:` line per file. The path MUST be the workspace path from the manifest — never a `/tmp` path. Before the attachment, send one short message stating what was converted (e.g. "Đã chuyển `bao-cao.docx` → PowerPoint, 8 slides.") including the slide count for pptx targets.

Target turnaround is 5-10 minutes from receiving the file. Do not send progress updates in between; only the summary + attachment, or the error.
