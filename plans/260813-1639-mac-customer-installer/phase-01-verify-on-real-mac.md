---
phase: 1
title: "Verify on a real Mac"
status: verified-by-code-runtime-pending
priority: P1
effort: "2-3h"
dependencies: []
---

# Phase 1: Verify on a real Mac

> **Result: [reports/verify-mac-260813.md](reports/verify-mac-260813.md).**
> Hermes was not installed on the available machine, so verification was done by reading
> the upstream source (`github.com/NousResearch/hermes-agent` + the live `install.sh`),
> plus two items measured on real macOS 15.4. Findings carry one of two labels —
> **VERIFIED-BY-CODE** (`file:line`, evidence for a design decision) or **MEASURED**
> (executed here). A code read never counts as a hardware PASS.
>
> | Item | Result |
> |---|---|
> | A1 launchd | **PASS-BY-CODE** — label `ai.hermes.gateway`, `KeepAlive` already `<true/>` → P3's plist patch and `load -w` fallback both deleted |
> | A2 catch-up | 2h grace confirmed, **but a late job still runs once** → limitation #5 corrected |
> | A4 stdlib-only | **MEASURED PASS** — all 5 D1 suites pass on `/usr/bin/python3` 3.9.6 |
> | A6 cron TZ | **FAIL** — Hermes uses local/configured tz, not UTC. Real bug in `prepare_config.py`, now fixed |
> | A8 `--skip-setup` | **PARTIAL FAIL** — gateway prompt not suppressed; on macOS its yes-branch starts `nohup hermes gateway` (409 trap) |
> | A9 chat_id | **PASS-BY-CODE** — `TELEGRAM_HOME_CHANNEL` → watchdog is implementable |
> | skill interpreter | Hermes venv python, not a separate venv → changed P4/4.2 |
> | A3, A5, A7, `hermes update`, clean-Mac CLT dialog, install duration | **NOT-RUN** — field checklist at the end of the report |

## Overview

Hands-on spike on one Mac. **Blocks Phases 2–4.** Every assumption below comes from reading code plus web research — none has been executed. The customer confirmed a Mac is available, so this phase is no longer hypothetical.

Scope is fixed at **basic** (power on + log in) → **the entire `--system` LaunchDaemon / FileVault / auto-login branch is dropped**. Only needs to confirm a LaunchAgent works.

## Requirements

- Functional: confirm or refute 9 blocking assumptions.
- Non-functional: no product code changes in this phase; record findings only.

## Step 1 (do this first)

```bash
hermes gateway install --help     # record the plist path + label it creates (P3 needs it to patch KeepAlive)
hermes gateway install --start-now --start-on-login
launchctl print "gui/$UID/<label>"
pgrep -f "hermes gateway"          # expect: exactly 1 PID
```

## Assumptions to measure

| # | Assumption | How to measure | If wrong |
|---|---|---|---|
| A1 | `hermes gateway install` stands up a LaunchAgent on macOS | as in Step 1 | bootstrap exit 5 → try `launchctl load -w <plist>`. Still dead → re-decide gateway-run strategy (foreground/`nohup`) before writing P2–P3 |
| A2 | daily cron catch-up = 2h (`period//2` clamped to 7200s) | `*/5` job, kill gateway for 15 min, restart, count runs. Then a daily job: set delivery time 3h in the past, restart, see whether it fires | update limitation #5 in `plan.md` + handover docs |
| A3 | Gateway comes back after **logout → login** | log out, log back in, `pgrep -f "hermes gateway"` | `--start-on-login` not honored → P3 must handle it |
| A4 | D1 runs on Python stdlib + curl only (no pip) | clean Mac: `python3 skills/morning-report/tests/test_*.py`; `generate_audio_file.py` without ffmpeg | extra install step needed → heavier installer |
| A5 | `hermes setup` wizard works on macOS and accepts DeepSeek + Telegram | run it manually, record **every screen** to write the P2 guide | — |
| A6 | `hermes cron` uses system TZ (not UTC) | schedule a job 5 min out in local time, see if it fires correctly | fix `local_time_to_utc_cron` or document it |
| A7 | Firecrawl free tier covers 1–2 topics | sign up for real, read the dashboard quota (**1,000/month or 1,000 lifetime?**); run one real report, measure credits before/after | update the cost table in `plan.md`; tell the customer the real number |
| A8 | `--skip-setup` also suppresses the gateway prompt | `bash -s -- --skip-setup`, check whether it still asks "install gateway as background service?" (`maybe_start_gateway`, ~line 2471) | P2 must suppress the prompt another way, otherwise the customer **installs the gateway twice** = 409 Telegram |
| A9 | `.env` contains a variable holding the chat_id the watchdog can message | after `hermes setup`: `cut -d= -f1 ~/.hermes/.env` (**key names only, never values**) | no chat_id → **the P3 watchdog is unimplementable**, need another source |

## Also measure (non-blocking, needed for P2–P3)

- `python3 --version` on a clean macOS — does it trigger the Xcode CLT prompt?
- Path of `hermes` after install; does it append to `~/.zshrc` (install.sh ~line 1859)?
- What `hermes config env-path` returns
- Current `pmset -g` — how long before a desktop Mac sleeps by default (P3 needs the severity)
- Apple Silicon vs Intel: `brew --prefix` = `/opt/homebrew` or `/usr/local`
- Total install time from a clean machine (to set customer expectations)
- Run `hermes update`, then check whether the service stays down (known bug — decides whether the watchdog catches it)

## Related Code Files

- Read: `setup/scripts/02_install_hermes.sh`, `skills/morning-report/scripts/prepare_config.py` (`sync_cron_jobs`, `local_time_to_utc_cron`), `collect_sources.py` (`target_fetched=5`, `fetch_with_fallback` retries ×2)
- Create: `plans/260813-1639-mac-customer-installer/reports/verify-mac-260813.md`

## Implementation Steps

1. Prepare a test Mac (prefer a fresh user account or VM to simulate a clean machine).
2. `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`, record all output plus every macOS dialog.
3. Run `hermes setup`, capture each screen.
4. **Step 1** above — record the plist path + label (P3 needs them).
5. Measure A1 → A9.
6. Write the report; update `plan.md` if any number differs.

## Success Criteria

- [ ] LaunchAgent stands up, `pgrep` returns **exactly 1 PID**, plist path + label recorded for P3
- [ ] Logout → login → gateway comes back
- [ ] Report gives PASS/FAIL for A1–A9 with real output (no speculation)
- [ ] Measured daily catch-up window + Firecrawl credits per run, written into `plan.md`
- [ ] Default `pmset sleep` value known
- [ ] Exact list of macOS dialogs the customer will encounter

## Risk Assessment

- **No clean Mac available** → results from a dev machine (already has brew/python/CLT) are falsely optimistic. Mitigation: fresh macOS user or VM.
- **A1 FAIL** (LaunchAgent won't stand up) → gateway-run strategy must be re-decided with the customer before writing P2–P3 code. This is why the phase blocks.
- A7 materially wrong (Firecrawl is lifetime, not monthly) → the customer starts paying after ~2 months; report it early rather than at acceptance.
