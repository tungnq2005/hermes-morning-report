---

name: morning-report
description: Use when the user asks to set up, run, generate, test, check status, troubleshoot, pause, disable, resume, or update the daily Morning Report delivered to Telegram, or to turn a report they already received into a Google Doc, Google Slides deck, or PDF.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [morning-report, daily-briefing, telegram, audio, cron]
    related_skills: [doc-convert, guided-setup]
required_environment_variables:

- EXA_API_KEY
- BRAVE_SEARCH_API_KEY
- FIRECRAWL_API_KEY

---

# Morning Report

Collects 24h updates for one or more configured topics via Exa search with Brave fallback, then sends a separate structured daily briefing to Telegram for each topic, with optional MP3 audio. Config in `state/topic-config.json`.

Missing or rejected search keys are a setup problem, not a report problem: hand off to `skill_view(name="guided-setup")`, which walks the user through getting a key and pastes it into place from chat. Never ask the user to edit `~/.hermes/.env` themselves.

## Workflow Router

Choose exactly one workflow below and follow it step by step.

- **Set up or update Morning Report config:** → [Update Config](#update-config)
- **Pause or resume the daily schedule:** → [Pause / Resume](#pause--resume)
- **Run / generate / test a report:** → [Run Report](#run-report)
- **Turn a report into a Google Doc / Slides / PDF (any report, any day):** → [Export Report](#export-report)
- **Check current state, cron status, or troubleshoot:** → [Status](#status)

---



## Update Config

Use when the user wants to set up Morning Report for the first time or change Morning Report config. Config is **per-topic**: each topic owns its own delivery time, timezone, style, language, audio, and channel, and maps to its own cron job and its own delivered report.

Supported flags:

| Setting          | Flag                                      |
| ---------------- | ----------------------------------------- |
| Change one topic | `--topic "<topic>"` (selector for field changes) |
| All topics       | `--all-topics` (apply field changes to every topic) |
| Add topic        | `--add-topic "<topic>"` (inherits defaults) |
| Remove topic     | `--remove-topic "<topic>"`                |
| Delivery time    | `--delivery-time "<time>"`                |
| Timezone         | `--timezone "<tz>"`                       |
| Report style     | `--report-style "<style>"`                |
| Report language  | `--report-language "<lang>"`              |
| Audio summary    | `--audio-summary "<Enabled|Disabled>"`    |
| Delivery channel | `--delivery-channel "<channel>"`          |
| Google Doc copy  | `--google-doc "<Enabled|Disabled>"`       |

Field changes (delivery time, timezone, style, language, audio, channel, Google Doc copy) require a target: `--topic "<topic>"` for one topic or `--all-topics` for every topic. Adding/removing topics uses `--add-topic`/`--remove-topic`.

`google_doc` (default `Disabled`) decides whether every delivered report is ALSO saved as a Google Doc, with the link sent under the report. Enable it when the user says something like "lưu bản tin vào Google Docs luôn" / "always save the report to Google Docs". Warn them once that it creates one file per report per day in their Drive, and that it needs Google connected. When it is off, the report can still be exported on demand — see [Export Report](#export-report).

Config-related requests:

- Set up Morning Report.
- Change, add, or remove topics.
- Change per-topic delivery time, timezone, report style, report language, audio summary, delivery channel, or the Google Doc copy toggle.
- Enable or update the daily schedule (one cron job per topic).

Not config-related:

- Run, generate, or test today's report.
- Ask for current status, cron status, recent history, or troubleshooting info.
- Ask how the skill works without requesting a config change.

### Step 0: Read current config and validate the request

Before applying any change, read the current status:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py
```

Read `available_config.topics` (current per-topic configs) and `missing_config`. Validate the user's request against it before proceeding:
- If the user names a topic that is not configured (and did not ask to add it), ask whether to add it first.
- If the request is ambiguous (e.g., "change the 9am report" but no topic is at 9am, or it is unclear which topic or field), ask for clarification.
- If a value is invalid (e.g., a style that is not `concise`, `deep_analysis`, or `opportunities_risks`), ask for a valid one.

Only proceed to Step 1 once the request is unambiguous and refers to existing or explicitly new topics.

### Step 1: Prepare config

Combine ALL requested changes into a single `prepare_config.py` call with the relevant flags. Run without `--save`.

Examples:

```bash
# Status (no changes)
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py
# Change one topic's style
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --topic "AI" --report-style "deep_analysis"
# Change a field for every topic
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --all-topics --timezone "Asia/Ho_Chi_Minh"
# Add / remove a topic
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --add-topic "Gold prices"
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --remove-topic "Weather"
```

Read the JSON output and follow `next_action`. Use `available_config.topics` as the per-topic config after applying the requested values. Present `requested_changes` as bullets and tell the user any `warnings`. Do not save until the user clearly confirms and `missing_config` is empty.

### Step 2: Save confirmed config

Only after the user confirms and the config is complete, rerun `prepare_config.py` with `--save --enable-cron` and the same config flags that should change:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --save --enable-cron <confirmed config flags>
```

Read the JSON output and follow `next_action`. Saving reconciles one cron job per configured topic: it creates jobs for new topics, removes jobs for removed topics (and the legacy single "Morning Report" job if present), and updates schedules when a topic's `delivery_time` or `timezone` changes. Each per-topic cron job runs only that topic and delivers its own report.

---



## Pause / Resume

Use when the user wants to pause or resume the daily Morning Report schedule without changing config. Config (`state/topic-config.json`) is preserved — all Morning Report cron jobs (one per topic) are toggled together.

### Step 1: Pause or resume the schedule

```bash
# Pause
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --pause-cron

# Resume
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --resume-cron
```

Read the JSON output and follow `next_action`. `cron_state` will be one of: `paused`, `resumed`, `no_job`, `already_paused`, `already_running`, `error`; `details` lists per-job results. Config is preserved on both pause and resume.

---



## Run Report

Use for manual, test, or cron report runs. Follow each step in order.

**Cron runs:** send no progress or acknowledgement messages before the final report.
**Manual runs:** at most one short acknowledgement before work begins.

**Single-topic cron runs:** each per-topic cron job is prompted to process only one topic. If the run is for a single topic, run Step 2 with `--topic "<that topic>"` once, then Steps 3–5 for it; do not loop over all configured topics.

**Final response content:** your final response is what gets delivered to Telegram. For each topic you process, your response MUST START with that topic's report title (the `# ` heading) and contain only: the `report.md` content verbatim (including the sources footer, whose heading is in the report language), then a line `MEDIA:<the audio MP3 output path from Step 4>` for its audio, then — only when Step 5 actually produced a Google Doc — one short final line carrying that link. Do NOT write any line before the title — no "All steps complete", no "Delivering the final report", no progress or announcement text, no summary.

### Step 1: Check config

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py
```

If `configured` is false, follow `next_action` and stop. If configured is true, keep the topic names from `available_config.topics` as `TOPICS`. Each topic in `TOPICS` must produce its own report, and its own audio when audio is enabled.

### Step 2: Collect sources for one topic

For each topic in `TOPICS`, run the rest of the Run Report workflow once:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/collect_sources.py --topic "<topic>"
```

Read the JSON output and follow `next_action`. Keep the returned `topic` and `run_dir` for the current topic.



### Step 3: Validate and send report

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/validate.py \
  --type report \
  --report-file "<run_dir from Step 2 output>/report.md" \
  --style "<style>" \
  --language "<report_language from config>" \
  --run-dir "<run_dir from Step 2 output>"
```

`--language` is what catches English headings on a non-English report — use the exact
`report_language` value from config. Heading names per language are in
`references/report-styles.md`; do not invent your own.

Read the JSON output and follow `next_action`.



### Step 4: Validate, generate, and send audio

If audio is disabled, skip audio for the current topic and continue with the next topic.

1. Write audio script from report facts → `<run_dir from Step 2 output>/audio-script.txt`

2. Validate:
```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/validate.py \
  --type audio --text-file "<run_dir from Step 2 output>/audio-script.txt" \
  --run-dir "<run_dir from Step 2 output>"
```
- `ok: true` → continue to MP3 generation.
- `ok: false` with `report_not_validated` / `report_changed_after_validation` → Step 3 did
  not finish, or the report was edited afterwards. Go back and re-run Step 3; do not
  generate audio from a report that has not passed.
- `ok: false` with `under_min_words` → expand the script; aim for ~780 words (middle of the 680-930 range). Re-validate.
- `ok: false` with `over_max_words` → trim the script; cut redundant details, keep key facts. Re-validate.
- Word-count balancing often takes 2-3 rounds — this is normal. If still failing after 3 attempts, use the closest passing revision and skip MP3.

3. Generate MP3 — name it per topic with a **safe filename** (ASCII lowercase, hyphens, no spaces/diacritics; you choose the slug, e.g. "Giá vàng Mỹ" → `gia-vang-my` or `gold-us`):

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/generate_audio_file.py \
  --text-file "<run_dir from Step 2 output>/audio-script.txt" \
  --speed 1.2 --strict-length \
  --lang "<language from config>" \
  --output "<run_dir from Step 2 output>/morning-report-<safe-topic-slug>.mp3" \
  --run-dir "<run_dir from Step 2 output>"
```

4. Send audio as media (use the `--output` path from Step 4.3):
```
MEDIA:<run_dir from Step 2 output>/morning-report-<safe-topic-slug>.mp3
```

### Step 5: Google copy

Read `google_doc` for the current topic from the Step 1 config output.

**`google_doc` is `Enabled`** — save this report to the user's Drive as part of the run:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py \
  --run-dir "<run_dir from Step 2 output>" --to gdoc \
  --image-query "<short English query for section 1>" \
  --image-query "<short English query for section 2>"
```

One `--image-query` per section of the report, in section order, always in English —
see [Export Report](#export-report) for why.

On `success`, append ONE short line after the `MEDIA:` line with the `google_url` as a
clickable link. If it fails, still deliver the report and audio — a missing Google copy
must never swallow the report. On a cron run say nothing about the failure; on a manual
run add one short line saying the Google copy could not be made, and follow the
`next_action` (a `google_unauthorized` result means the user should be offered the
in-chat Google connection).

**`google_doc` is `Disabled`** (the default) — do not create anything.
- **Manual run:** you may add exactly ONE short line after `MEDIA:` offering a Google
  Docs/Slides copy of this report. If the user says yes, follow [Export Report](#export-report).
- **Cron run:** add nothing — the delivered message must match the "Final response content" rule above.

Never call `convert.py` yourself here: `export_report.py` records the export on the run,
so asking for the same report twice returns the same file instead of filling the user's
Drive with duplicates.

---



## Export Report

Use when the user wants an already-generated report as a Google Doc, Google Slides, or
PDF — "gửi bản tin sáng nay dạng Google Docs", "làm slide từ bản tin crypto hôm qua",
"xuất bản tin ra PDF". This works for ANY stored report, not just the one from this
conversation: reports live in `state/history/<date>/<run>/report.md`.

This is the Morning Report → Document Conversion hand-off. Run it from this skill; do
not ask the user to attach a file they never had.

### Step 1: Pick the report

If the user clearly means the most recent report ("bản tin sáng nay", "cái vừa gửi"),
skip straight to Step 2. If they are vague or you need to confirm which one:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --list
```

Read the JSON output and follow `next_action`. Show topic + date + time, never
directory paths.

### Step 2: Export it

```bash
# newest report
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --to gdoc
# a specific topic, newest first (matches the topic name or the report title)
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --topic "crypto" --to gdoc
# one particular day
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --date 2026-08-19 --to gslides
# the run you just produced in Run Report
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --run-dir "<run_dir>" --to gdoc
```

Targets: `gdoc` (document, default), `gslides` (slides), `pdf`, `docx`, `md`.
Choose `gslides` only when the user asks for slides/presentation.

**Always pass pictures for `gdoc` and `gslides`.** Add one `--image-query` per section
of the report, in section order — and write each query in **short, concrete English**,
even when the report is Vietnamese: the image library indexes almost nothing under
Vietnamese, so a Vietnamese query returns nothing (or fishing boats). Translate each
section heading; pass `--image-query ""` for a section that deserves no picture:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py \
  --run-dir "<run_dir>" --to gdoc \
  --image-query "gold bars" \
  --image-query "federal reserve building" \
  --image-query ""
```

`images_used` in the output says how many actually landed. Zero with an
`image_search_no_result:*` warning means the queries found nothing — say so plainly if
the user asks, and offer to retry with different words. Use `--no-auto-images` only when
the user wants a plain document.

Read the JSON output and follow `next_action`. On success send `google_url` as a
clickable link plus a standalone `MEDIA:<output>` line for the PDF copy — and do not
paste the report text again, the user already has it.

`reused: true` means this report was exported before and the same file is being
returned on purpose. Say so; only pass `--again` if the user explicitly wants a
separate new file.

---



## Status

Use when the user asks "what is my morning report config?", "is it running?", "when is my next report?", or for troubleshooting.

### Step 1: Show configuration

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py
```

Read the JSON output. Present `available_config`, whether `configured` is true, and any fields in `missing_config`.

### Step 2: Show cron status

```bash
# Check for Morning Report cron job — use cronjob tool:
cronjob(action='list')
```

If a "Morning Report" job exists, show its schedule and whether it is **active** or **paused**. If paused, tell the user the report is not being sent and they can resume it by asking to resume the morning report. If active, mention they can pause it by asking to pause the morning report. If no job exists, say "no daily schedule is set up."

### Step 3: Show recent history (optional)

Check if any recent runs exist:

```bash
ls ~/.hermes/skills/productivity/morning-report/state/history/ 2>/dev/null | tail -5
```
