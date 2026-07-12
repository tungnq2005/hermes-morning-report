---
name: doc-convert
description: >
  Convert documents and presentations between formats for Hermes.
  Use this skill when the user sends a file (Word .docx, PowerPoint .pptx, PDF, text, Markdown)
  or a Google Drive / Google Docs / Google Slides link and asks to convert it to another format
  (PowerPoint, Word, PDF, Markdown), to summarize it into slides, or to narrate it as audio.
  Routes to the skill prompts and keeps all outputs inside the workspace.
---

# Document Conversion Skill

Use this skill as the router for the Document & Presentation Conversion use case.

## Workflow Router

- Convert a document/presentation to another format (docx/pptx/pdf/md): `skills/doc-convert/prompts/convert.md`
- Narrate a document/presentation as an audio summary (MP3): `skills/doc-convert/prompts/narrate.md`
- Check runtime readiness or troubleshoot: run `python3 skills/doc-convert/scripts/preflight.py --compact` and report the JSON findings.

## State And Helpers

- Outputs: `skills/doc-convert/state/output-history/YYYY-MM-DD/<run-id>/` (one directory per conversion run, contains outputs + `manifest.json`)
- Audio narration history: `skills/doc-convert/state/audio-history/`
- Helper scripts: `convert.py`, `narrate.py`, `preflight.py`, `doc_io.py`, `build_pptx.py`

Do not hand-write output files when a helper script can produce them.

## Guardrails

- Supported inputs: `.docx`, `.pptx`, text-based `.pdf`, `.txt`, `.md`, and public Google Drive / Docs / Slides links. Scanned/image-only PDFs are not supported; say so instead of guessing content.
- Video generation/editing is out of scope. Decline politely.
- All generated files must live under `skills/doc-convert/state/`. NEVER write deliverables to `/tmp` and NEVER send a `MEDIA:` directive pointing outside the workspace — the gateway blocks local media from outside allowed workspace directories.
- Always send results as Telegram attachments via a standalone `MEDIA:<absolute-path>` line, one per file.
- Use the user's language for conversation; keep generated content in the document's own language unless the user asks otherwise.
- Google Workspace access is available when `preflight` shows `google.authorized_token: true`: private Docs/Slides/Drive links are read via the authorized API, and `--to gdoc`/`gslides` create cloud drafts. If NOT authorized, private links fail — then ask the user to enable link sharing ("Anyone with the link") or upload the file directly. Never claim OAuth access without verifying via preflight.
- Report conversion failures honestly with the helper's error output. Do not fabricate output paths.
