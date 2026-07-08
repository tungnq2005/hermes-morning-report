# Audio

Use only when audio summary is enabled.

## Script

- Write `/tmp/morning-report-audio.txt`.
- Use the same facts and sources as the text report.
- Do not copy/shorten the text report as the whole script.
- Target: 650-900 words. Below 600 words the MP3 lands under the 3-minute floor.
- Natural spoken language. No URLs, tables, source labels, debug text, file paths, or hype.

Length math: the MP3 is sped up with `--speed 1.2` (ffmpeg `atempo`) *after* TTS, so the
delivered audio is shorter than a raw `words / 180` estimate. Measured end-to-end rate on
the delivered MP3 is **189 wpm**, so `--wpm 189` is what makes `estimated_minutes` match
reality. At 189 wpm the contracted 3-5 minute band is **567-945 words**; the gates below
sit just inside it.

Validate before TTS:

```bash
python3 skills/morning-report/scripts/report/validate_audio_script.py \
  --text-file /tmp/morning-report-audio.txt \
  --min-words 600 \
  --max-words 930 \
  --wpm 189
```

If validation fails, revise once. If it still fails, skip MP3 and send the audio-failure notice.

## MP3

Dry-run:

```bash
python3 skills/morning-report/scripts/report/generate_audio_file.py \
  --text-file /tmp/morning-report-audio.txt \
  --lang "<configured-report-language>" \
  --speed 1.2 \
  --min-words 600 \
  --max-words 930 \
  --wpm 189 \
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
  --min-words 600 \
  --max-words 930 \
  --wpm 189 \
  --chunk-limit 180 \
  --strict-length
```

Use JSON `output` for Telegram and `history_dir/manifest.json` for report history.

Send audio as one standalone line:

```text
MEDIA:<mp3-output-path>
```

If audio fails after text delivery, send one short notice in the configured report language.
