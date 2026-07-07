# Morning Report Update

Use for topic, schedule, style, language, audio, channel, or status updates.

After every script command, follow `next_action`.
Run `next_action.command` when present.
For `command_template`, fill only explicit user-requested flags.
If confirmation is required, show `changed_fields` and `display_config`, then wait.
After confirmation, run `next_action.after_confirmation.command`.
Use `skills/morning-report/references/cron.md` for scheduler actions.
Do not invent settings or claim unverified scheduler/audio/Telegram behavior.

## Start

Run:

```bash
python3 skills/morning-report/scripts/update/run.py --agent check-config
```