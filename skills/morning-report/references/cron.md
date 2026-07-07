# Cron Setup

Use the native OpenClaw CLI on this Ubuntu VPS.

Command prefix:

```bash
openclaw
```

Do not use Docker Compose or `openclaw-cli` in this native setup.

Cron commands talk to the OpenClaw Gateway. If a shell command returns `GatewaySecretRefUnavailableError`, do not conclude that cron is missing. Use a gateway-resolved command path, pass a supported `--token`, or ask the operator to fix secret resolution. Do not write tokens or secrets into workspace files.

## Known Commands

| Command | Purpose |
|---|---|
| `status` | Scheduler status |
| `list` | List jobs |
| `get` | Show one job as JSON |
| `show` | Show one job in formatted output |
| `add` | Add a new job |
| `edit` | Patch job fields through options |
| `disable` | Disable a job |
| `enable` | Enable a disabled job |
| `rm` | Remove a job |
| `run` | Run a job immediately for debugging |
| `runs` | Show run history |

Do not use unknown command names such as `create`, `update`, `remove`, `pause`, or `delete`.

There is no standalone `wake` command. Wake is an option on `add` or `edit`:

```bash
openclaw cron edit <job-id> --wake now
openclaw cron edit <job-id> --wake next-heartbeat
```

## Important Options

Use `openclaw cron add --help` and `openclaw cron edit --help` if exact flags need confirmation.

Common `add` options:

- `--name`, `--cron`, `--tz`, `--message`
- `--session`, `--session-key`
- `--channel`, `--to`, `--announce`
- `--model`, `--thinking`, `--tools`, `--light-context`
- `--timeout-seconds`
- `--disabled`
- `--wake`

Common `edit` options:

- `--name`, `--cron`, `--tz`, `--every`, `--at`
- `--disable`, `--enable`, `--wake`
- `--model`, `--message`, `--system-event`
- `--channel`, `--to`, `--announce`, `--webhook`
- `--session`, `--session-key`
- `--tools`, `--thinking`, `--light-context`
- `--timeout-seconds`
- `--failure-alert` with sub-options
- `--delete-after-run`, `--keep-after-run`

Use `cron edit` for schedule patches after the target job is verified.

## Model Override Is Not Fallback

`cron add --model` and `cron edit --model` set the primary model for the cron job.

Do not use `--model` to configure fallback from the existing primary model.

For model/provider fallback setup, read:

`skills/morning-report/references/model-fallback.md`

## Inspect First

Before adding, changing, disabling, enabling, removing, or resuming a schedule:

```bash
openclaw cron status
openclaw cron list --all
```

If a `Morning Report` schedule already exists, do not create a duplicate. Preserve and patch the existing job by default.

Use `cron get <job-id>` for machine-readable verification and `cron show <job-id>` for human-readable inspection:

```bash
openclaw cron get <job-id>
openclaw cron show <job-id>
```

## Cron Expression

Convert confirmed delivery time to cron format:

- `07:00` -> `0 7 * * *`
- `07:30` -> `30 7 * * *`

## Add

Use `cron add`, not `cron create`.

Before first use, inspect the current CLI syntax if exact flags are not already known:

```bash
openclaw cron add --help
```

Required Morning Report values for a new job:

- name: `Morning Report`
- schedule: confirmed cron expression and timezone
- message/workflow points to `skills/morning-report/prompts/run-report.md`
- session: `isolated`
- channel: Telegram
- target: actual Telegram target, not a placeholder

Command shape:

```bash
openclaw cron add \
  --name "Morning Report" \
  --cron "<cron-expression>" \
  --tz "<timezone>" \
  --message "Read and execute skills/morning-report/prompts/run-report.md. Generate the Morning Report using the confirmed report language and deliver it through Telegram." \
  --session isolated \
  --announce \
  --channel telegram \
  --to "<telegram-target-id>"
```

Do not guess `<telegram-target-id>`. Use only the actual Telegram target from the current OpenClaw runtime/session.

## Edit Or Reschedule

If a `Morning Report` job already exists and the delivery time, timezone, workflow message, channel, model, or session settings must change:

1. Inspect the job with `cron get <job-id>`.
2. Verify it is the `Morning Report` job and points to `skills/morning-report/prompts/run-report.md`.
3. Patch only the required fields with `cron edit <job-id> ...`.
4. Verify the edited job with `cron get <job-id>` or `cron show <job-id>`.

Example:

```bash
openclaw cron edit <job-id> \
  --cron "<cron-expression>" \
  --tz "<timezone>"
```

Do not remove and re-add a schedule when `cron edit` can safely patch it.

## Disable Or Enable

Use `cron disable <job-id>` to pause a verified job. Use `cron enable <job-id>` to re-enable it.

```bash
openclaw cron disable <job-id>
openclaw cron enable <job-id>
```

Before disabling or enabling:

- verify the job with `cron get <job-id>`
- verify it is the `Morning Report` job
- verify the workflow points to `skills/morning-report/prompts/run-report.md`
- preserve saved topics and preferences in `skills/morning-report/state/current-topics.md`

## Remove

Use `cron rm <job-id>` only after the user/operator clearly confirms permanent removal, replacement cleanup, or a reset.

Do not use `rm` for ordinary topic changes or temporary pause/disable when `cron disable` is available.

Before removing:

- verify the job with `cron get <job-id>`
- verify it is the `Morning Report` job
- verify the workflow points to `skills/morning-report/prompts/run-report.md`
- preserve saved topics and preferences in `skills/morning-report/state/current-topics.md`

## Verify

After adding, editing, disabling, enabling, removing, or replacing a schedule:

```bash
openclaw cron list --all
openclaw cron get <job-id>
openclaw cron runs --id <job-id>
```

For active schedules, treat cron setup as successful only after verification shows:

- job name: `Morning Report`
- confirmed cron expression
- confirmed timezone
- `isolated` session mode
- workflow/message points to `skills/morning-report/prompts/run-report.md`
- Telegram delivery is enabled
- Telegram target is real, not a placeholder
- job is enabled

For disabled schedules, treat pause/disable as successful only after verification shows the `Morning Report` job exists and is disabled.

For removed schedules, treat removal as successful only after verification shows the old job is no longer listed or no longer retrievable as an active job.

## Pause, Disable, Or Resume

For pause/disable:

1. Confirm the user's intent.
2. Inspect scheduler state.
3. Verify the target job is exactly `Morning Report`.
4. Disable the cron job with `cron disable <job-id>`.
5. Verify the job is disabled.
6. Set Morning Report lifecycle status to `paused` or `disabled` with `scripts/update_config.py set-status`.

If `cron disable` is unavailable or cannot be verified:

- still set Morning Report lifecycle status to `paused` or `disabled`
- do not claim that the cron job itself was disabled
- the run workflow must stop before report generation while status is `paused` or `disabled`

For resume/re-enable:

1. Inspect scheduler state with `cron list --all`.
2. If the existing `Morning Report` job exists, enable it with `cron enable <job-id>`.
3. If no valid job exists, add a new `Morning Report` job using the saved delivery time/timezone and verified Telegram target.
4. Verify the active schedule with `cron list --all` and `cron get <job-id>`.
5. Set lifecycle status back to `configured` only after scheduler verification succeeds.

For temporary pause with automatic resume, use only verified runtime support. Wake is an `add` or `edit` option, not a standalone command.
