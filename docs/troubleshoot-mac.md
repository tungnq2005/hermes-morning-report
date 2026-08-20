# Troubleshooting (Mac)

There is no remote access to this Mac, so every diagnosis starts the same way:
**run one command and send the result to support.**

## The one command

Open Terminal (`Cmd` + `Space`, type `Terminal`) and run:

```bash
hermes-check
```

Copy everything it prints and send it. It contains no API keys or tokens — only the
names of the keys, never their values.

If Terminal says `command not found: hermes-check`, run this instead:

```bash
bash ~/.hermes/morning-report-src/setup/scripts/healthcheck_hermes.sh
```

---

## The 5 things that actually go wrong

### 1. No report arrived this morning

Most likely: the Mac slept, was off, or nobody was logged in.

```bash
pmset -g custom | grep -E '^\s*sleep'     # must show 0
```

If it shows anything other than 0:

```bash
sudo pmset -a sleep 0 disksleep 0
```

Then ask the bot in Telegram: **"send report"** — you get today's report immediately.

### 2. The bot does not answer in Telegram at all

```bash
hermes-check
```

Look at the `gateway pid` line:

- **0** → the bot is not running: `hermes gateway start`
- **2 or more** → two copies are running, which makes Telegram drop messages:

  ```bash
  launchctl bootout gui/$(id -u)/ai.hermes.gateway
  pkill -f 'hermes_cli.main.* gateway'
  hermes gateway start
  ```

  Then check `hermes-check` shows 1.

### 3. A Telegram message from the watchdog: "the bot is not working"

The watchdog already tried restarting and it did not help. Run `hermes-check` and send
the output. Common causes it cannot fix by itself: no internet, a DeepSeek account out
of balance, a full disk.

A message saying **"working again"** means it recovered on its own — nothing to do.

### 4. The report arrives but has no audio, or the audio is broken

The voice track uses a free service and can fail without breaking the report.
Check that ffmpeg is present:

```bash
command -v ffmpeg || brew install ffmpeg
```

### 5. Sending a document does nothing / "soffice not found"

The document conversion part is not installed or has lost its dependencies (a Hermes
update can rebuild the Python environment). Re-run the add-on — it is safe to run
again at any time:

```bash
bash ~/.hermes/morning-report-src/setup/install-doc-addon.sh
```

Verify:

```bash
python3 ~/.hermes/skills/doc-convert/scripts/preflight.py --compact
```

`"success": true` means it is ready.

---

## Reading the health check output

| Problem shown | Meaning | Fix |
|---|---|---|
| `gateway_not_running` | The bot is not running | `hermes gateway start` |
| `multiple_gateway_processes:2` | Two copies are running; Telegram drops messages | See section 2 |
| `launchagent_not_loaded` | It will not restart by itself after login | `hermes gateway install --force` |
| `launchd_unsupported_fallback` | macOS refused to supervise the bot; it runs but will not survive a restart | Send this to support |
| `machine_can_sleep:30` | Sleep is back on — reports will stop | `sudo pmset -a sleep 0 disksleep 0` |
| `no_recent_report_26h` | No report in over a day | Sections 1 and 2 |
| `doctor_not_clean` | Hermes reports a configuration problem | `hermes doctor` and send the output |
| `low_disk` | Under 1 GB free | Free up space |

Note: for the first 26 hours after installing, `no_recent_report_26h` is suppressed on
purpose — a brand-new machine has not delivered anything yet and that is not a fault.

---

## Files support may ask for

| File | What it is |
|---|---|
| `~/hermes-install.log` | Everything the installer did (keys are masked) |
| `~/.hermes/logs/gateway.error.log` | Errors from the bot itself |
| `~/.hermes/logs/watchdog.log` | What the watchdog saw and did |

## Restarting everything from scratch

```bash
hermes gateway stop
hermes gateway start
hermes-check
```

If that does not help, re-running the installer is safe: it keeps your keys and
settings and repairs whatever is missing.
