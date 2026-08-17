---
title: One-command macOS installer for customer machines (Hermes Morning Report)
status: in_progress
created: 2026-08-13
updated: 2026-08-13
scope: project
blockedBy: []
blocks: []
---

> **Status 2026-08-13.** Phase 1 verified statically against the upstream Hermes source
> (report: [reports/verify-mac-260813.md](reports/verify-mac-260813.md)); Phases 2-4 are
> implemented. Runtime items that need a real machine and real API accounts are still
> open — see the NOT-RUN table in the report. Three findings changed this plan and are
> folded in below: launchd needs no patching, a late login loses nothing, and
> `prepare_config.py` had a real cron-timezone bug (now fixed).

# One-command macOS installer for customer machines

**Fixed context:**
- Machine: **Mac Studio / Mac mini, always on**, with a logged-in user session.
- Scope: **basic** — power on + log in and it runs. No power-outage handling, no UPS, no remote access.
- Report topics: **1–2 maximum**.
- Installs **both D1 + D2**. Customer supplies their own API accounts and manages their own credit.
- All installer output, prompts, and handover docs: **English only**.

## Answers to the original questions

**1. Is `setup_all_hermes.sh` good enough? → NO.** It is a VPS-Ubuntu installer. On macOS, 4 of 6 scripts break:

| Script | On macOS | Reason |
|---|---|---|
| `config.env.example` | **Fails silently** | `getent passwd` does not exist on macOS → `OC_HOME` falls back to `/home/mac` (nonexistent) → keys written to a path nothing reads |
| `01_system_prep` | **Breaks** | `apt`, `loginctl enable-linger`, `pip3 --break-system-packages` all absent |
| `02_install_hermes` | **Works** | Hermes installer supports Darwin + brew; `gateway install` uses launchd (known bugs, see P1/P3) |
| `03_setup_env` | Works | only writes `~/.hermes/.env` — but depends on the broken `OC_HOME` above |
| `04_bootstrap_skill` | **Half breaks** | D2 tests need `python-docx/pptx/pypdf` which aren't installed; `set -e` aborts the whole installer |
| `05_searxng` | Not needed | Docker; MR uses Exa/Brave directly |
| `healthcheck` | **Breaks** | `systemctl --user` does not exist on macOS |

**2. Remaining limitations after fixing scope to "basic":**

Basic scope (power on + log in) removes most of the risk: a LaunchAgent in `gui/$UID` runs correctly whenever a login session exists → **no LaunchDaemon, no disabling FileVault, no auto-login needed**. Two items remain, and both need code, not configuration:

- **The machine must not sleep.** macOS puts desktops to sleep after tens of minutes by default → the gateway process suspends → no report delivered. `sudo pmset -a sleep 0` is mandatory.
- **Nobody notices when the gateway dies.** Known launchd bug: after `hermes update` the service stays down (launchd reads exit 0 as "don't relaunch"). Without an alert the customer discovers it days later.

**3. Lightest approach:** one line pasted into Terminal (not a double-clickable `.command` — that carries Gatekeeper quarantine), an English wizard that asks for each key with a signup link and validates it on the spot. D1 first, D2 via `install-doc-addon.sh` run right after (**still part of standard handover**; split only so a LibreOffice/brew failure can't take down the morning report).

## API cost — effectively free at 1–2 topics

Each report: 1 search + ~5–10 fetches. At 2 topics × 1/day × 30 days:

| Service | Est. monthly use | Free tier | Verdict |
|---|---|---|---|
| Exa | ~60 searches | 20,000 req/month, no card | **Well within free** |
| Firecrawl | ~400–600 credits | 1,000 credits/month | **Sufficient** (ceiling ~3 topics) |
| DeepSeek | a few cents | no free tier | **Needs prepaid balance**, but very cheap |
| Brave | optional | has free tier | Can be left blank |

→ At 1–2 topics the "no extra cost" goal **is met**, except DeepSeek requires a prepaid balance (a few dollars per year). Customer supplies the accounts and manages credit. P1 re-confirms the free tiers at signup time (Firecrawl has flip-flopped between "1,000 lifetime" and "1,000/month").

## Full limitation list (for handover)

| # | Limitation | Severity | Mitigation |
|---|---|---|---|
| 1 | macOS sleeps → gateway suspends → no report | **High** | `pmset -a sleep 0` in installer (P3); healthcheck reads `pmset -g custom` and flags it if it comes back |
| 2 | Service stays down after `hermes update` | **High** | Upstream already emits `KeepAlive=true` and retries bootstrap (bootout+retry, registration confirmed via `launchctl list`), so **no plist patch and no `launchctl load -w`** — see P1 report A1. Residual risk is covered by the watchdog |
| 3 | Gateway dies unnoticed | **High** | Watchdog alerts Telegram directly, bypassing Hermes (P3). `chat_id` source confirmed: `TELEGRAM_HOME_CHANNEL` |
| 4 | Reboot (power loss / macOS update) → someone must log in again | Medium | **Accepted, in scope.** Documented so the customer knows |
| 5 | Logging in more than 2h after delivery time makes the report **late**, not lost | Medium | Corrected by P1/A2 (`cron/jobs.py:2880-2908`): past the 2h grace window the job collapses missed slots and **still runs once immediately**. Documented in `limits-mac.md`; the customer can also message "send report" |
| 5b | `hermes cron` evaluates schedules in Hermes' local/configured timezone, not UTC | **High** | **Was a real bug**: `prepare_config.py` emitted UTC cron → every report 7h off on a Mac in ICT. Fixed — the schedule is now emitted in Hermes' effective timezone (`HERMES_TIMEZONE` → `config.yaml` → system local). VPS behaviour unchanged because its effective tz *is* UTC |
| 6 | Customer registers 3–4 APIs themselves (DeepSeek needs prepaid balance) | Medium | wizard with links + on-the-spot validation; cost table above |
| 7 | Customer creates the bot via @BotFather, copies a long token | Medium | validate via `getMe`, print bot name for confirmation |
| 8 | Customer can't read logs when something fails | Medium | `~/hermes-install.log`; `hermes-check` prints one copy-paste block |
| 9 | `convert.py:163` calls bare `soffice` — the macOS cask doesn't put it on PATH | Medium | add-on symlinks it (P4) |
| 10 | No remote access → every issue handled over the phone | Low | **Accepted, in scope.** `hermes-check` gives a copy-pasteable block |
| 11 | Disk full / hardware failure | Low | healthcheck |

**Out of scope (customer decided not to handle):** power outage/UPS, auto-login after reboot, `--system` LaunchDaemon, Tailscale/SSH remote access.

## Phases

| # | Phase | Status | Description |
|---|---|---|---|
| 1 | [Verify on a real Mac](phase-01-verify-on-real-mac.md) | verified by code, runtime pending | A1/A2/A4/A6/A8/A9 + skill interpreter answered ([report](reports/verify-mac-260813.md)). A3/A5/A7 + `hermes update` still need a real machine and real accounts |
| 2 | [Installer + English wizard](phase-02-installer-and-wizard.md) | implemented | `setup/install-mac.sh` + `lib/wizard-prompts.sh` + `lib/validate-api-keys.sh` |
| 3 | [Runtime reliability while logged in](phase-03-runtime-reliability.md) | implemented | `lib/setup-launchd.sh`, `lib/setup-watchdog.sh`, macOS branch in `healthcheck_hermes.sh`, `hermes-check` |
| 4 | [doc-convert add-on + handover docs](phase-04-doc-convert-addon-and-handover.md) | implemented | `install-doc-addon.sh` chained at step 10 + `docs/{install,limits,troubleshoot}-mac.md` + both READMEs |

## Principles

- **One run installs BOTH skills.** `install-mac.sh` installs morning-report, then chains `install-doc-addon.sh` at step 10 as a trapped subprocess. Neither skill counts as installed until verified: both directories present as real copies, `preflight.py` passes, `hermes doctor` sees both, plus a live report and a `.docx` → `.pptx` round-trip. The split is failure isolation only — D2 is not optional.
- **Do not generate a `config.env`.** Every variable already has a default; the file only creates the `getent` trap on macOS and adds two manual steps for the customer.
- **Copy skills, don't symlink.** If the customer deletes or moves the downloaded folder, the skills die silently.
- **Never write a parallel plist** alongside `hermes gateway install`. Telegram allows exactly one long-poller per bot token → two gateways = 409 Conflict, duplicated or dropped messages. **Do not patch the plist either** — `launchd_plist_is_current()` rewrites hand edits on the next install/start, and `KeepAlive` is already `<true/>`.
- **Only pipe the Hermes `install.sh` when `hermes` is absent.** It always runs its own gateway prompt, and on macOS the yes-branch starts `nohup hermes gateway` (no systemd found) — a second long-poller, i.e. the 409 above arriving by accident on the second run.
- **The watchdog must live OUTSIDE Hermes.** A process cannot report its own death.
- **Acceptance = a real report delivered by the real cron path**, not `ok:true`. The DeepSeek key and bot token are entered inside `hermes setup`, beyond our validation reach.
- Don't run the 102 unit tests in the customer install path (one flaky test aborts everything). Put them behind a `--dev` flag.
- **Stay inside basic scope.** Don't add auto-login / LaunchDaemon / remote access — the customer explicitly declined them.
- **English only** in installer output, prompts, code comments, and handover docs. Scope of this rule: everything **new or modified** by this plan — `install-mac.sh`, `install-doc-addon.sh`, `setup/lib/*`, the three new `docs/*-mac.md`, and the sections of `README.md` / `setup/README.md` this plan touches. Pre-existing Vietnamese material outside that set (`docs/user-guide.vi.md`, `docs/operator-runbook.vi.md`, `docs/chat-commands.md`, the VPS scripts under `setup/scripts/`) is **left as is** unless separately requested.

## Dependencies / blocking risks

- ~~Phase 1 must finish before 2–4~~ — **cleared.** The go/no-go question ("can `hermes gateway install` stand up a LaunchAgent on macOS?") is answered PASS from the upstream source: label `ai.hermes.gateway`, plist `~/Library/LaunchAgents/ai.hermes.gateway.plist`, bootstrap into `gui/$UID` with retry and a detached fallback. No strategy change needed, so P2–P4 were written.
- ~~Not yet confirmed whether `hermes cron` uses system TZ or UTC~~ — **answered: Hermes' configured/local tz** (`hermes_time.py`), and the skill was fixed accordingly.
- Remaining risk is **runtime only**: nothing in this plan has been executed on a Mac with Hermes installed. The NOT-RUN table in the P1 report is the field checklist; run it during handover before declaring the machine accepted.

## Open questions

1. **A7 — is the Firecrawl free tier 1,000 credits per month or 1,000 total?** Only answerable by signing up. If it is one-off, 2 topics exhaust it in ~2 months and the customer must upgrade. Who signs up, and when?
2. Who runs the NOT-RUN checklist (A3 logout/login, A5 wizard screens, `hermes update` behaviour), and on which machine — a staging Mac or the customer's during handover?
3. The one-line install command needs a real host for `install-mac.sh` (currently `https://<host>/install-mac.sh`, with `MR_REPO_TARBALL` defaulting to the GitHub tarball of `tungnq2005/openclaw-morning_report@main`). Which host, and is that repo public?
