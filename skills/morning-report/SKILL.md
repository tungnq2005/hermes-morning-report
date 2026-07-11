---

name: morning-report
description: Use when the user asks to set up, run, generate, test, check status, troubleshoot, pause, disable, resume, or update the daily Morning Report delivered to Telegram.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [morning-report, daily-briefing, telegram, audio, cron]
    related_skills: []
required_environment_variables:

- EXA_API_KEY
- FIRECRAWL_API_KEY

---

# Morning Report

Collects 24h topic updates via Exa and sends a structured daily briefing to Telegram, with optional MP3 audio. Config in `state/topic-config.json`.

## Workflow Router

Choose exactly one workflow below and follow it step by step.

- **Set up or update Morning Report config:** → [Update Config](#update-config)
- **Run / generate / test a report:** → [Run Report](#run-report)
- **Check current state, cron status, or troubleshoot:** → [Status](#status)

---



## Update Config

Use when the user wants to set up Morning Report for the first time or change Morning Report config.

Supported flags:

| Setting          | Flag                                      |
| ---------------- | ----------------------------------------- |
| Topic            | `--topic "<topic>"`                       |
| Delivery time    | `--delivery-time "<time>"`                |
| Timezone         | `--timezone "<tz>"`                       |
| Report style     | `--report-style "<style>"`                |
| Report language  | `--report-language "<lang>"`              |
| Audio summary    | `--audio-summary "<Enabled|Disabled>"`    |
| Delivery channel | `--delivery-channel "<channel>"`          |

Config-related requests:

- Set up Morning Report.
- Change topic, delivery time, timezone, report style, report language, audio summary, or delivery channel.
- Enable or update the daily schedule.

Not config-related:

- Run, generate, or test today's report.
- Ask for current status, cron status, recent history, or troubleshooting info.
- Ask how the skill works without requesting a config change.

### Step 1: Prepare config

Combine ALL requested changes into a single `prepare_config.py` call with all relevant flags. Run without `--save`.

Examples:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --topic "World Cup" --report-language "English"
```

Read the JSON output and follow `next_action`. Use `available_config` as the Morning Report config after applying the requested values. Do not save until the user clearly confirms and `missing_config` is empty.

### Step 2: Save confirmed config

Only after the user confirms and the config is complete, rerun `prepare_config.py` with `--save --enable-cron` and the same config flags that should change:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --save --enable-cron <confirmed config flags>
```

Read the JSON output and follow `next_action`. Saving includes creating the Morning Report cron job if it does not exist, or updating the existing cron job when `delivery_time` or `timezone` changes.

---



## Run Report

Use for manual, test, or cron report runs. Follow each step in order.

**Cron runs:** send no progress or acknowledgement messages before the final report.
**Manual runs:** at most one short acknowledgement before work begins.

### Step 1: Check config and collect sources

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/collect_sources.py
```

Read the JSON output and follow `next_action`.



### Step 2: Validate and send report

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/validate.py \
  --type report \
  --report-file "<run_dir from Step 1 output>/report.md" \
  --style "<style>" \
  --run-dir "<run_dir from Step 1 output>"
```

Read the JSON output and follow `next_action`.



### Step 3: Validate, generate, and send audio

If audio is disabled, stop here.

1. Write audio script from report facts → `<run_dir from Step 1 output>/audio-script.txt`

2. Validate:
```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/validate.py \
  --type audio --text-file "<run_dir from Step 1 output>/audio-script.txt"
```
- `ok: true` → continue to MP3 generation.
- `ok: false` with `under_min_words` → expand the script; aim for ~780 words (middle of the 680-930 range). Re-validate.
- `ok: false` with `over_max_words` → trim the script; cut redundant details, keep key facts. Re-validate.
- Word-count balancing often takes 2-3 rounds — this is normal. If still failing after 3 attempts, use the closest passing revision and skip MP3.

3. Generate MP3:

```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/generate_audio_file.py \
  --text-file "<run_dir from Step 1 output>/audio-script.txt" \
  --speed 1.2 --strict-length \
  --lang "<language from config>" \
  --output "<run_dir from Step 1 output>/morning-report.mp3" \
  --run-dir "<run_dir from Step 1 output>"
```

4. Send audio as media:
```
MEDIA:<run_dir from Step 1 output>/morning-report.mp3
```

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

If a "Morning Report" job exists, show its schedule and enabled status. If not, say "no daily schedule is set up."

### Step 3: Show recent history (optional)

Check if any recent runs exist:

```bash
ls ~/.hermes/skills/productivity/morning-report/state/history/ 2>/dev/null | tail -5
```
