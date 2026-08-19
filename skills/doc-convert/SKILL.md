---
name: doc-convert
description: >
  Convert documents and presentations for Hermes, delivering the result as Google Slides
  or Google Docs. Use this skill when the user sends a file (Word .docx, PowerPoint .pptx,
  PDF, text, Markdown) or a Google Drive / Google Docs / Google Slides link and asks to
  convert it, to summarize it into slides, or to narrate it as audio. Decks and documents
  are built in Google so they look the same on macOS, Windows, iPad and the browser; any
  .pptx/.docx/.pdf the user wants is exported back out of Google.
---

# Document Conversion Skill

Use this skill as the router for the Document & Presentation Conversion use case.

## Google Is The Deliverable

A deck built by python-pptx renders differently in PowerPoint for Mac than it does on
the VPS, so the file this skill builds is no longer what the user receives. Every
conversion (except `md`) is imported into Google Slides / Google Docs, and the user
gets the Google link — plus a PDF exported by Google as the offline copy. When the user
asks for a `.pptx`/`.docx`/`.pdf` file, that file is Google's export, not our own
render. `convert.py` does this automatically; you do not orchestrate the upload.

Without an authorized Google token this degrades to local rendering with a
`google_unauthorized:rendered_locally` warning in the manifest — say so when it happens
instead of shipping a file that may look wrong on the user's Mac.

## Workflow Router

- Convert a document/presentation (default target: Google Slides / Google Docs): `skills/doc-convert/prompts/convert.md`
- Narrate a document/presentation as an audio summary (MP3): `skills/doc-convert/prompts/narrate.md`
- Check runtime readiness or troubleshoot: run `python3 skills/doc-convert/scripts/preflight.py --compact` and report the JSON findings.

## State And Helpers

- Outputs: `skills/doc-convert/state/output-history/YYYY-MM-DD/<run-id>/` (one directory per conversion run, contains the delivered file + `manifest.json`; `build/` holds the intermediate that was uploaded to Google)
- Audio narration history: `skills/doc-convert/state/audio-history/`
- Helper scripts: `convert.py`, `narrate.py`, `preflight.py`, `validate_output.py`, `doc_io.py`, `build_pptx.py`

Do not hand-write output files when a helper script can produce them.

## Guardrails

- Supported inputs: `.docx`, `.pptx`, text-based `.pdf`, `.txt`, `.md`, and public Google Drive / Docs / Slides links. Scanned/image-only PDFs are not supported; say so instead of guessing content.
- Video generation/editing is out of scope. Decline politely.
- All generated files must live under `skills/doc-convert/state/`. NEVER write deliverables to `/tmp` and NEVER send a `MEDIA:` directive pointing outside the workspace — the gateway blocks local media from outside allowed workspace directories.
- Deliver the `google_url` from the manifest as a clickable link, and send the exported PDF as a Telegram attachment via a standalone `MEDIA:<absolute-path>` line, one per file. Files created in Google stay private to the user's own Drive — never change sharing without being asked.
- Use the user's language for conversation; keep generated content in the document's own language unless the user asks otherwise.
- Google Workspace access is available when `preflight` shows `google.authorized_token: true`: private Docs/Slides/Drive links are read via the authorized API, and every non-`md` target is rendered in Google. If NOT authorized, private links fail and output falls back to local rendering — then ask the user to run `authorize_google.py`, or to enable link sharing ("Anyone with the link") for the input. Never claim OAuth access without verifying via preflight.
- Report conversion failures honestly with the helper's error output. Do not fabricate output paths or Google URLs.
- Check `google_check.status` in the manifest for slide targets, and run `validate_output.py` on every file before sending it. Viewing a rendered preview is not verification. `unchecked` is not a pass. If a check fails, fix it or tell the user which check failed — never ship a silent failure.
