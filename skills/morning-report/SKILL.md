---
name: morning-report
description: >
  Set up, run, check, troubleshoot, pause, disable, resume, and update the Telegram Morning Report workflow for OpenClaw.
  Use this skill when the user asks to configure a daily morning report, generate or test a report,
  change tracked topics, pause/disable/resume reports, view current topics/preferences, inspect schedule/cron status, troubleshoot
  missing reports or audio summaries, or manage Morning Report runtime state. Routes to the skill prompts
  and preserves confirmed user configuration.
---

# Morning Report Skill

Use this skill as the router for the Morning Report use case.
Choose exactly one prompt below, read it, and follow it before acting.

## Workflow Router

- Setup, configure, enable, or finish onboarding: `skills/morning-report/prompts/setup.md`
- Run, generate, preview, test, or scheduled-run a report: `skills/morning-report/prompts/run-report.md`
- View or change topics, delivery time, timezone, style, language, audio, delivery channel, pause, disable, resume, or mixed fields: `skills/morning-report/prompts/update.md`
- Check current state, cron status, delivery status, or troubleshoot report/audio: `skills/morning-report/prompts/status.md`

If an update is pending and the user sends another change instead of confirming, rerun the update preview with the merged explicit changes.

For internal model/provider fallback setup or troubleshooting, read `skills/morning-report/references/model-fallback.md` before changing runtime model configuration.

## State And Helpers

- Runtime state: `skills/morning-report/state/current-topics.md` (local, git-ignored, created by setup)
- User preference summary: `USER.md`
- Runtime artifacts: `skills/morning-report/state/audio-history/`, `skills/morning-report/state/report-history/`, `skills/morning-report/state/audit.log`
- Helper scripts: `setup/run.py`, `report/run.py`, `report/source_collection.py`, `report/web_source_collector.py`, `report/validate_report_text.py`, `report/validate_audio_script.py`, `report/generate_audio_file.py`, `report/record_report_history.py`, `report/record_audio_history.py`, `report/history_status.py`, `report/audit_events.py`, `update/run.py`, `config_status.py`, `report_style.py`, `tts_languages.py`, `update_config.py`

Do not manually rewrite runtime state, report history, audit log, or audio artifacts when a helper script can perform the update.

## Guardrails

- Do not assume topics, delivery time, timezone, report language, report style, audio preference, Telegram target, cron status, TTS availability, or fallback model/provider status.
- Use the user's language during setup, status, and topic update conversations.
- Use the configured report language during report generation.
- Do not ask the customer to edit files, code, Docker, or VPS settings.
- Do not claim cron, audio, Telegram delivery, or fallback behavior is ready unless verified by the relevant workflow.
- Keep internal model/provider fallback details out of customer-facing confirmations unless the operator explicitly asks.
