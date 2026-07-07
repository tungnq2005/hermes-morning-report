# Morning Report Status

Use for current config, topics, cron status, report history, audio status, or troubleshooting.

## Check

Always run:

```bash
python3 skills/morning-report/scripts/config_status.py
```

Use helper JSON as source of truth.

If runtime readiness matters:

```bash
python3 skills/morning-report/scripts/setup/run.py --compact
```

If latest report/audio matters:

```bash
python3 skills/morning-report/scripts/report/history_status.py --limit 1
```

Read `cron.md` only for scheduler troubleshooting.
Read `model-fallback.md` only for fallback troubleshooting.

## Output

Keep concise. Include available:

- status
- topics
- delivery time
- timezone
- style
- language
- audio
- channel
- cron status, only if inspected
- latest report/audio status, only if inspected

Do not edit files or scheduler state.
Say `unknown` or `not verified` when not inspected.
