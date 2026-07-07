# Audio

Use only when audio summary is enabled.

## Script

- Write `/tmp/morning-report-audio.txt`.
- Use the same facts and sources as the text report.
- Do not copy/shorten the text report as the whole script.
- Target: 540-900 words.
- Natural spoken language. No URLs, tables, source labels, debug text, file paths, or hype.

Validate before TTS:

```bash
python3 skills/morning-report/scripts/report/validate_audio_script.py \
  --text-file /tmp/morning-report-audio.txt \
  --min-words 540 \
  --max-words 900 \
  --wpm 180
```

If validation fails, revise once. If it still fails, skip MP3 and send the audio-failure notice.

## MP3

Dry-run:

```bash
python3 skills/morning-report/scripts/report/generate_audio_file.py \
  --text-file /tmp/morning-report-audio.txt \
  --lang "<configured-report-language>" \
  --speed 1.2 \
  --min-words 540 \
  --max-words 900 \
  --wpm 180 \
  --chunk-limit 180 \
  --strict-length \
  --dry-run
```

Generate:

```bash
python3 skills/morning-report/scripts/report/generate_audio_file.py \
  --text-file /tmp/morning-report-audio.txt \
  --lang "<configured-report-language>" \
  --speed 1.2 \
  --min-words 540 \
  --max-words 900 \
  --wpm 180 \
  --chunk-limit 180 \
  --strict-length
```

Use JSON `output` for Telegram and `history_dir/manifest.json` for report history.

Send audio as one standalone line:

```text
MEDIA:<mp3-output-path>
```

If audio fails after text delivery, send one short notice in the configured report language.
