# Manual QA Checklist

Run this checklist after major Morning Report prompt or script changes. Pair it with:

```bash
python3 -m unittest discover skills/morning-report/tests
python3 skills/morning-report/scripts/setup/run.py --compact
```

## Router And Status

- [ ] Ask what topics Morning Report is tracking. The agent routes to `prompts/status.md`.
- [ ] The response lists active topics, delivery time, timezone, style, report language, audio preference, and delivery channel.
- [ ] The agent does not edit files or scheduler state for a status-only request.
- [ ] Unknown cron, Telegram, TTS, or fallback status is stated as unknown or not verified.
- [ ] Fallback troubleshooting reads `references/model-fallback.md` and does not use `cron edit --model` as fallback setup.

## Setup

- [ ] Start from `Status: not_configured` in `state/current-topics.md`.
- [ ] `scripts/setup/run.py --compact` reports runtime readiness without changing report configuration.
- [ ] Ask the agent to set up Morning Report. It asks only for missing required values.
- [ ] The setup question uses the user's language.
- [ ] Before saving, the agent summarizes the full resulting configuration: topics, delivery time, timezone, style, language, audio, and Telegram.
- [ ] If the user sends another configuration change instead of confirming, the agent merges the change and asks for confirmation again.
- [ ] After clear confirmation, the agent saves via `scripts/update_config.py`, syncs `USER.md`, then verifies with `scripts/config_status.py --check`.
- [ ] The agent claims Morning Report is enabled only after cron/scheduler is configured and verified.

## Topic And Settings Updates

- [ ] Replacing topics requires confirmation and shows `current -> requested`.
- [ ] The confirmation lists all resulting settings; it does not say only "other settings stay the same."
- [ ] Topic update final response lists previous topics -> new topics plus delivery time, timezone, style, language, audio, and channel.
- [ ] Adding or removing a topic uses `scripts/update_config.py ... --sync-user`.
- [ ] Removing the final active topic is blocked; the agent asks whether to replace it or disable Morning Report explicitly.
- [ ] If the user changes delivery time or timezone, the agent routes to `prompts/update.md`.
- [ ] Report style aliases such as `brief`, `deep analysis`, and `risks` are saved as `concise`, `deep_analysis`, and `opportunities_risks`.
- [ ] Time or timezone changes update and verify cron before the agent says the schedule is enabled.
- [ ] Internal fallback model/provider details are not mentioned to the customer.

## Pause, Disable, And Resume

- [ ] Disable Morning Report after confirmation. Topics and preferences remain saved.
- [ ] If cron disable cannot be verified, the agent says scheduler status is not verified.
- [ ] While status is `disabled` or `paused`, manual/scheduled report runs stop before search or generation.
- [ ] Resume/re-enable only after `cron enable` or `cron add` is verified active.
- [ ] After resume, status returns to `configured` and `USER.md` status returns to `enabled`.

## Manual Report Run

- [ ] A manual run starts with `scripts/config_status.py --check`.
- [ ] If required config is missing, the agent stops before search or report generation.
- [ ] A scheduled/cron run sends no progress or acknowledgement messages before the final report.
- [ ] A manual test run sends at most one short acknowledgement before work begins.
- [ ] The agent does not send phase updates such as search progress, composing, audio success, history recording, or delivery status.
- [ ] The report uses only configured topics, configured language, configured style, and fresh sources from the current run.
- [ ] `concise` reports use Morning Brief structure and stay scan-friendly.
- [ ] `deep_analysis` reports use Morning Analysis structure with key developments, implications, and watch next.
- [ ] `opportunities_risks` reports use opportunities, risks, watchlist, and suggested actions.
- [ ] The text report passes `scripts/report/validate_report_text.py` before delivery.
- [ ] The text report is sent before audio generation or audio delivery.
- [ ] The customer-facing Telegram text report starts directly with the report title.
- [ ] The agent does not send a second summary or recap after the report unless the user explicitly asks.
- [ ] After generation, the agent records history with `scripts/report/record_report_history.py`.

## Audio

- [ ] If audio is disabled, no audio script or MP3 is generated.
- [ ] If audio is enabled, the agent creates `/tmp/morning-report-audio.txt` as a separate spoken script from the same current-run facts and sources.
- [ ] The audio script passes `scripts/validate_audio_script.py` before TTS.
- [ ] If validation fails, the agent revises the audio script once before skipping MP3 generation.
- [ ] The agent passes the configured report language to `generate_audio_file.py --lang` for both dry-run and TTS.
- [ ] The audio manifest `requested_lang` and normalized `lang` match the configured report language for the run.
- [ ] Audio validation reports `word_count`, `estimated_minutes`, and any issues.
- [ ] If audio validation or TTS dry-run fails, text delivery remains successful and MP3 generation is skipped for that run.
- [ ] If audio generation succeeds, the Telegram chat receives a standalone `MEDIA:<mp3-path>` message after the text report.
- [ ] The Telegram chat receives an attached/playable MP3, not just a text path.
- [ ] Text report delivery still succeeds if audio generation fails.
- [ ] If audio generation fails, the agent sends one short customer-visible audio-failure notice.
- [ ] Audio success or failure is reflected in report history.
- [ ] The full audio script is not included in the customer-facing text report unless explicitly requested.

## Artifacts

- [ ] `state/audit.log` gains an event after setup, topic updates, settings updates, or report recording.
- [ ] `state/history/` stores one folder per run with report, source manifest, audio artifacts, and manifest.
- [ ] Runtime artifacts remain ignored by git.
