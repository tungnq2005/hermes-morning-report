---
phase: 3
title: "Runtime reliability while logged in"
status: implemented
priority: P1
effort: "0.5-1d"
dependencies: [1, 2]
---

# Phase 3: Runtime reliability while logged in

> **Implemented** in `setup/lib/setup-launchd.sh`, `setup/lib/setup-watchdog.sh` and the
> macOS branch of `setup/scripts/healthcheck_hermes.sh`. **Two steps of 3.1 below were
> deleted, not implemented** — the P1 report shows upstream already does both, better:
>
> - ~~3.1 step 2, `launchctl load -w` fallback~~ — upstream retries bootstrap with
>   bootout-and-retry, confirms registration via `launchctl list`, and degrades to a
>   detached process behind a marker file. Legacy `load` on top risks a duplicate
>   registration. We detect the marker instead and warn that restart-survival is lost.
> - ~~3.1 step 3, patch `KeepAlive` to boolean~~ — it is already `<true/>`
>   (`gateway.py:4276`), and `launchd_plist_is_current()` rewrites hand edits on the next
>   install/start, so the patch would be both pointless and temporary.
>
> Kept and implemented: exactly-one-PID assertion (catching both the LaunchAgent spelling
> and a `nohup hermes gateway` stray), `pmset -a sleep 0 disksleep 0` with read-back from
> `pmset -g custom` (not `pmset -g`, which reports transient assertions), the 15-minute
> watchdog calling `healthcheck_hermes.sh` → `launchctl kickstart -k` → direct Telegram
> `curl`, one alert per incident plus a recovery message, and `hermes-check`.
>
> Two corrections found while reviewing, both now implemented:
>
> - **The watchdog is installed after the step-9 acceptance test, not in step 7.** With
>   `RunAtLoad` + a 15-minute interval, an earlier install would see a machine with no
>   report yet (or sleep still on, if the customer declined the sudo prompt), restart the
>   gateway mid-test and message the customer "the bot is not working" during handover.
>   `hermes-check` is still installed in step 7, because step 9 tells the customer to run it.
> - **`machine_can_sleep` no longer triggers the restart-and-alert cycle.** It is real but a
>   restart cannot fix it and the bot is not broken; it gets its own one-off advisory
>   message with the `pmset` command to run. Only gateway-level problems alert.
> - Both the watchdog and the healthcheck **probe `gui/$UID` then `user/$UID`** rather than
>   assuming gui, matching upstream `_launchd_domain()`.
>
> Also added to the healthcheck: the post-install 26h grace window, duplicate-gateway
> detection, `launchagent_not_loaded`, the launchd-unsupported marker, and a `sleep != 0`
> check. `config.env` is now sourced only if present, so the same script runs on both
> hosts. **Not run:** `kill -9` recovery, logout/login, the 2h idle test, a live alert.

## Overview

Fixed scope: **power on + log in and it runs**. No power-outage handling, no auto-login, no LaunchDaemon, no remote access. Three items remain — but all three are mandatory; dropping any one makes reports stop arriving silently.

## Key insight

With a login session always present, a LaunchAgent in `gui/$UID` is sufficient. Two things can still kill the system:

1. **macOS sleep** — desktops sleep after tens of minutes by default; the gateway process suspends with them.
2. **A process cannot report its own death** — any alerting that runs *inside* Hermes is useless exactly when it's needed.

## Requirements

- Functional: machine never sleeps; gateway recovers from crashes; logging back in restores it.
- Functional: gateway down → Telegram alert within 15 minutes, **not routed through Hermes**.
- Non-functional: **never** create a parallel plist alongside `hermes gateway install`.

## Architecture

### 3.1 LaunchAgent — patch what exists, don't create a rival

```
hermes gateway install --start-now --start-on-login
```

Telegram allows exactly **one long-poller per bot token**; two gateways = 409 Conflict, duplicated or dropped messages. Therefore:

1. Run the command above (it writes the canonical plist).
2. If `launchctl bootstrap` fails with exit 5 (known bug) → fall back to `launchctl load -w <the plist hermes just wrote>`.
3. Patch **that plist** so `KeepAlive` is a **boolean `true`**, NOT the default dictionary form `{SuccessfulExit: false}` — the dict form is precisely what makes launchd read exit 0 as "finished, don't relaunch", the root of the "service stays down after `hermes update`" bug (#28135). launchd throttles respawn to ~10s.
4. Verify: `pgrep -f "hermes gateway"` returns **exactly 1 PID**.

### 3.2 Prevent sleep

```
sudo pmset -a sleep 0 disksleep 0
sudo pmset -a displaysleep 10        # screen off is fine, machine sleep is not
```

Needs sudo → ask the customer once during install, explain why in plain English (without this, reports stop arriving with no error). Verify after setting: `pmset -g | grep -E "^ *sleep"` must show `0`.

**Out of scope (customer declined):** `autorestart 1`, `womp 1`, disabling macOS auto-update. After a reboot someone must log in again; document it, don't code around it.

### 3.3 Watchdog outside Hermes

~10 lines, its own LaunchAgent with `StartInterval=900`, running as the customer's user, **independent of Hermes**:

```
every 15 minutes:
  bash healthcheck_hermes.sh   → ok:true?
  ├─ yes → exit quietly
  └─ no  → launchctl kickstart -k gui/$UID/<label>
           wait 60s, run healthcheck again
           still ok:false → curl POST api.telegram.org/bot<TOKEN>/sendMessage
                            "Bot on <machine> is failing: <problems>. Restart did not help."
```

**Call `healthcheck_hermes.sh`; do not hand-roll a `pgrep` check.** `pgrep` only catches a *dead* process. On a machine running for months the likelier silent failure is a *wedged* one: alive, long-polling stalled, producing no reports — `pgrep` passes forever while the customer receives nothing. `healthcheck` already has the "report within the last 26h" check that catches exactly this, plus the grace window that prevents fresh-install false alarms. Reuse it and cover both failure modes.

Alerts go via `curl` straight to the Telegram API — **never through the gateway**. This is the only thing that catches the `hermes update` bug leaving the service down; without it the customer discovers the outage days later. Given the no-remote-access scope, it's also the only channel by which they learn anything is wrong.

Anti-spam: alert once per incident (marker `~/.hermes/.watchdog-alerted`), send one recovery message when it comes back.

**Needs a `chat_id`, not just the token.** `sendMessage` requires `chat_id`; read it from `~/.hermes/.env` (likely `TELEGRAM_ALLOWED_USERS`, but **P1/A9 must confirm the real variable name** — without it the watchdog is unimplementable).

Use a LaunchAgent (not a Daemon) — same login session as the gateway, simpler and correct for this scope.

### 3.4 macOS healthcheck

Rewrite `healthcheck_hermes.sh` (the current one dies on `systemctl --user`):

| Check | Linux (keep) | macOS (new) |
|---|---|---|
| gateway running | `systemctl --user is-active` | `pgrep -f "hermes gateway"` + `launchctl print` |
| doctor clean | `hermes doctor` | unchanged |
| recent report | `find -mmin -1560` | unchanged (macOS `find` supports `-mmin`) |
| free disk | `df -Pk` | unchanged |
| **machine not sleeping** | — | `pmset -g` → `sleep` must be 0 |

Also add:

- **Post-install grace window**: marker `~/.hermes/.installed-at`; suppress the `no_recent_report_26h` red flag for the first 26h (otherwise the customer sees `ok:false` right after installing and calls support).
- Detect **more than one** gateway process → error (the 409 Telegram trap).
- `hermes-check` in `~/.local/bin` → prints one compact block the customer can copy to support. **Critical given no remote access** — it's the only way we can diagnose anything.

## Related Code Files

- Modify: `setup/scripts/healthcheck_hermes.sh` (add macOS branch, keep Linux branch)
- Create: `setup/lib/setup-launchd.sh` (3.1 — install + `load -w` fallback + KeepAlive patch + verify single PID)
- Create: `setup/lib/setup-watchdog.sh` (3.3 — LaunchAgent + watchdog script)
- Modify: `setup/install-mac.sh` (call both libs + `pmset` from 3.2)

## Implementation Steps

1. `setup-launchd.sh` per the four steps in 3.1; test with `kill -9` → must come back as exactly 1 PID.
2. `pmset` in `install-mac.sh` (request sudo, explain why, verify after setting).
3. `setup-watchdog.sh`: LaunchAgent every 15 min; test by killing the gateway and blocking restart → must receive the Telegram alert.
4. Patch `healthcheck_hermes.sh`: `case "$(uname -s)"`; add grace window + duplicate-process check + `pmset sleep` check.
5. Install `hermes-check` into `~/.local/bin`.
6. Test matrix: `kill -9` / logout-login / `hermes update` / two gateways at once / leave the machine idle 2h to confirm it doesn't sleep.

## Success Criteria

- [ ] `kill -9` the gateway → back up in < 60s, exactly 1 PID
- [ ] Log out and back in → gateway comes back
- [ ] Leave the machine untouched for 2h → does not sleep, report still delivered on time
- [ ] Block gateway restart → Telegram alert received within 15 minutes
- [ ] **Temporary cron 5 min out → report arrives unattended** (acceptance through the real delivery path, not a hand-run script)
- [ ] Wedged gateway (PID alive but producing no reports) → watchdog still alerts (thanks to healthcheck instead of `pgrep`)
- [ ] Run `hermes update` → service doesn't stay down (or the watchdog recovers it)
- [ ] `hermes-check` right after install → `ok:true` (no red flag for the missing report)
- [ ] `healthcheck_hermes.sh` still passes on Ubuntu (VPS path intact)

## Risk Assessment

- **409 Telegram if the launchd logic is wrong** → duplicated/dropped messages, hard to diagnose. Mitigation: verify exactly 1 PID; healthcheck flags > 1; the watchdog must `kickstart`, **never** spawn a new process.
- **Customer refuses the sudo prompt for `pmset`** → machine sleeps, reports stop silently. Mitigation: explain clearly; healthcheck detects and reports it.
- **Watchdog needs the bot token** → reads from `~/.hermes/.env`; must never log the token.
- If P1/A2 measures a catch-up window other than 2h → update the number in the handover docs.

## Security Considerations

- Watchdog runs as the customer's user (not root), reads a chmod 600 `.env`, never echoes the token.
- No ports opened, no remote-access software installed — matching the scope the customer set.
