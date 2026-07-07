# Run Morning Report

Use for manual, test, scheduled, or cron report runs.

- Scheduled runs: no progress messages.
- Manual runs: at most one short acknowledgement before work.
- Use only configured topics, fetched sources, configured language, and configured style.
- Send no second recap after sending.

## Follow JSON

After every script command, follow `next_action`.

- Run `next_action.command` when present.
- After completing a non-command action, run `next_action.next_command` when present.
- If no command is present and `can_continue` is false, stop.

If history recording fails, do not change the customer-facing report.

## Start

Run:

```bash
python3 skills/morning-report/scripts/report/run.py search --agent
```
