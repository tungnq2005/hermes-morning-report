# Narrate Document As Audio

Use this prompt when the user asks for an audio version / audio summary of a document or presentation.

## Steps

1. Run readiness check: `python3 skills/doc-convert/scripts/preflight.py --compact`. Stop with an honest explanation if `environment_ok` is false.
2. Build the narration script:

```bash
python3 skills/doc-convert/scripts/narrate.py --input "<path-or-url>" --lang "<language>"
```

Use the document's own language for `--lang` unless the user asks otherwise (accepts names like `Vietnamese`, `English`, or codes like `vi`, `en`).

3. Parse the JSON. On success it contains `script_path` and a ready-to-run `suggested_tts_command`. Run that command exactly as given — it writes the MP3 into `skills/doc-convert/state/audio-history/` (an allowed media path).
4. Take the final MP3 path from the TTS helper output / its manifest.

## Deliver

Send one short message naming the document, then attach the audio:

```text
MEDIA:<absolute-mp3-path-from-tts-output>
```

Never use `/tmp` paths in `MEDIA:` directives. If TTS fails, do not retry more than once; tell the user the narration failed this time and keep the script file for troubleshooting.
