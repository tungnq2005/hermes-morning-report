# Phase 1 verification — macOS (2026-08-13)

**Method.** Hermes is **not installed** on this machine (`command -v hermes` → not found, no `~/.hermes`).
Full runtime measurement was therefore impossible. Instead: shallow-cloned the upstream source
(`github.com/NousResearch/hermes-agent`, public) plus the live `install.sh`, and read the launchd /
cron / setup code paths. Two items were measured locally on real macOS.

Evidence labels used below:

- **VERIFIED-BY-CODE** — read from upstream source, `file:line` cited. Evidence for a design decision, **not** a hardware PASS.
- **MEASURED** — actually executed on this Mac (macOS 15.4, arm64).
- **NOT-RUN** — still needs a real machine / real API accounts. Command given.

Machine used for MEASURED items: macOS 15.4 (24E248), Darwin arm64, `brew --prefix` = `/opt/homebrew`.
Upstream files quoted are in the scratchpad clone; line numbers are from the commit cloned 2026-08-13.

---

## Headline results (read this first)

1. **A1 PASS-BY-CODE — launchd is fully supported.** Better than the plan assumed. Label
   `ai.hermes.gateway`, plist `~/Library/LaunchAgents/ai.hermes.gateway.plist`, `KeepAlive` is
   **already `<true/>`**. → **P3's plist patch and `launchctl load -w` fallback must both be dropped.**
2. **A6 FAIL — real bug.** Hermes evaluates cron expressions in its **configured/local** timezone, not
   UTC. Our `prepare_config.py:local_time_to_utc_cron` emits UTC → on a Mac in Asia/Ho_Chi_Minh every
   report fires **7 h off**. Works on the VPS only because the VPS system clock is UTC. Needs a decision.
3. **A2 — plan limitation #5 is wrong.** Past the 2 h grace window the job is **not** lost: it
   fast-forwards the missed slots and **still runs once immediately**. The report arrives late, not never.
4. **A8 — `--skip-setup` does not suppress the gateway prompt**, and on macOS the "yes" branch runs
   `nohup hermes gateway &` (not `gateway install`) → a second long-poller → the 409 we are designing
   against. Only pipe `install.sh` when `hermes` is absent.
5. **P4/4.2 answered — no separate venv.** Skill scripts run under the **Hermes venv python**
   (`<install>/venv/bin` is first in the service PATH), so doc-convert deps belong in that venv.

---

## A1 — `hermes gateway install` on macOS → **PASS (VERIFIED-BY-CODE)**

`hermes_cli/gateway.py:7140` — on macOS the install handler calls `launchd_install(force)`.

| Fact | Value | Source |
|---|---|---|
| Label | `ai.hermes.gateway` (`ai.hermes.gateway-<profile>` when a profile is used) | `gateway.py:3798` |
| Plist path | `~/Library/LaunchAgents/ai.hermes.gateway.plist` (real account home via `pwd`, not `$HOME`) | `gateway.py:2601,2612` |
| Domain | probed: `gui/$UID` preferred, `user/$UID` fallback, cached per process | `gateway.py:3809` |
| `ProgramArguments` | `<venv python> -m hermes_cli.main gateway run --replace` | `gateway.py:4202` |
| `RunAtLoad` | `<true/>` | `gateway.py:4273` |
| **`KeepAlive`** | **`<true/>` — unconditional, already the boolean form** | `gateway.py:4276` |
| `ThrottleInterval` | 30 s (raised from launchd's 10 s default) | `gateway.py:4283` |
| `ExitTimeOut` | 25 s | `gateway.py:4286` |
| `LimitLoadToSessionType` | `Aqua`, `Background` | `gateway.py:4267` |
| Logs | `~/.hermes/logs/gateway.log`, `gateway.error.log` | `gateway.py:4289` |

`launchd_install()` (`gateway.py:4523`) writes the plist **and** bootstraps it; `RunAtLoad` starts it.
It already handles every failure mode P3 planned to hand-roll:

- stale-label EIO → `bootout` + retry (`_launchctl_bootstrap`, `gateway.py:3920`)
- bootstrap "exited 0 but not registered" → retry until `launchctl list` confirms (`gateway.py:4012`)
- domain genuinely unsupported → writes an unsupported marker and falls back to a detached process
  (`_launchd_fallback_to_detached`, `gateway.py:4147`)
- plist drifted from the generated one → `launchd_plist_is_current()` / `refresh_launchd_plist_if_needed()`
  **rewrites it** on the next `install`/`start` (`gateway.py:4299`)

### Consequences for Phase 3 (plan corrections)

- **Drop 3.1 step 3 (patch `KeepAlive`).** It is already `<true/>`, so the patch is a no-op — and any
  hand-edit is reverted by the self-heal path on the next `hermes gateway start`. `gateway.py:4222`
  says this explicitly about manual plist edits.
- **Drop 3.1 step 2 (`launchctl load -w` fallback).** Legacy `load` against a label Hermes manages with
  `bootstrap`/`bootout` risks a duplicate registration; Hermes' own retry chain is strictly better.
- `--start-now` / `--start-on-login` are **parsed but ignored on macOS** (`subcommands/gateway.py:178,191`
  vs. `gateway.py:7140` → `launchd_install(force)` takes no such args). Harmless to pass; do not rely
  on them. Start-on-login comes from the LaunchAgent + `RunAtLoad` instead.
- Keep 3.1 step 4 (assert exactly 1 PID) and the watchdog. Those remain necessary.

**Still NOT-RUN:** that bootstrap actually succeeds on a customer Mac, and that `hermes update` does not
leave the service down. Commands: `hermes gateway install`, `launchctl print gui/$UID/ai.hermes.gateway`,
`pgrep -f "hermes gateway"`, then `hermes update` + re-check.

---

## A2 — catch-up window → **2 h confirmed, but the "lost report" claim is wrong (VERIFIED-BY-CODE)**

`cron/jobs.py:786` `_compute_grace_seconds()`: `grace = period // 2`, clamped to `[120 s, 7200 s]`.
A daily job → **7200 s = 2 h**. Matches the plan.

What the plan got wrong: `cron/jobs.py:2880-2908`. When a job is **past** its grace window it does not
skip the day — it re-anchors `next_run_at`, records a catch-up occurrence, and **falls through to
`due.append(job)`, executing once now**. Log line: *"missed its scheduled time … Running now"*.

→ **Limitation #5 in `plan.md` and `docs/limits-mac.md` should read:** logging in more than 2 h after
delivery time means the report arrives **late** (shortly after the gateway comes up), not that the day
is lost. Accumulated slots are collapsed to one run. **NOT-RUN:** confirm live (set delivery time 3 h in
the past, start the gateway, watch for one delivery).

---

## A6 — cron timezone → **FAIL (VERIFIED-BY-CODE). Bug in our own skill.**

`hermes_time.py` — Hermes' clock resolution order:

1. `HERMES_TIMEZONE` env var
2. `timezone` key in `~/.hermes/config.yaml`
3. **fallback: the machine's local time** (`datetime.now().astimezone()`)

`cron/jobs.py:41` imports that as `_hermes_now`, and croniter evaluates every schedule against it
(`cron/jobs.py:807,826`). So a cron expression is interpreted in **Hermes' effective timezone**.

Our `skills/morning-report/scripts/prepare_config.py:192` `local_time_to_utc_cron()` converts the
customer's delivery time to **UTC** before handing it to `hermes cron`. That is correct **only when
Hermes' effective timezone is UTC** — true on the Ubuntu VPS (system clock UTC, no `timezone` key),
which is why this has never surfaced.

On a customer Mac set to Asia/Ho_Chi_Minh with no `timezone` in `config.yaml`: 08:00 local → `0 1 * * *`
→ interpreted as **01:00 ICT**. **Every report fires 7 hours off.** P2's step-9 acceptance (temporary
cron 5 min out) would also fail for the same reason, so this blocks the installer.

Three fixes, all viable — needs a decision:

| Option | Change | Cost |
|---|---|---|
| **A. Make the skill timezone-aware** (recommended) | `local_time_to_utc_cron` → emit the cron expression in Hermes' *effective* tz (read `HERMES_TIMEZONE` → `config.yaml` → system local). VPS keeps emitting UTC because its effective tz *is* UTC → no regression | touches shared D1 code + its unit test; rename the function |
| B. Pin `HERMES_TIMEZONE=UTC` in the installer | no skill change | the **agent's** clock becomes UTC too → "today" is wrong in report prose before 07:00 ICT |
| C. Set `config.yaml timezone` = customer tz **and** emit local-time cron | correct clock *and* correct cron | still a skill change, plus an installer write; equivalent to A with extra state |

---

## A8 — `--skip-setup` and the gateway prompt → **PARTIAL FAIL (VERIFIED-BY-CODE)**

`install.sh:3419` calls `maybe_start_gateway` **unconditionally** — it is not gated on `RUN_SETUP`
(`install.sh:2490` only skips `run_setup_wizard`). So `--skip-setup` does **not** suppress it.

It does return early (`install.sh:2525`) when `$HERMES_HOME/.env` holds no messaging token
(`TELEGRAM_BOT_TOKEN`, … ; the literal `your-token-here` placeholder is excluded). Therefore:

- **First install on a clean Mac + `--skip-setup`** → no token in `.env` → **no prompt**. Good.
- **Any re-run after our wizard has written the token** → prompt *"Would you like to install the gateway
  as a background service?"* appears. And on macOS `command -v systemctl` fails, so the "yes" branch
  does **not** run `hermes gateway install` — it runs
  `nohup hermes gateway > ~/.hermes/logs/gateway.log 2>&1 &` (`install.sh:2610`). That is a **second
  long-poller** next to our LaunchAgent → **409 Conflict, dropped/duplicated Telegram messages**.

**P2 requirement:** run the `curl install.sh | bash -s -- --skip-setup` step **only when
`command -v hermes` is absent**. On re-runs, skip it (or use `hermes update`). This is also what makes
P2's "Ctrl+C then re-run" criterion safe. Also confirmed: correct syntax is `bash -s -- --skip-setup`
(`install.sh:12`), and `~/.local/bin` is appended to `~/.zshrc` when missing (`install.sh:1854-1894`).

---

## A9 — chat_id for the watchdog → **PASS (VERIFIED-BY-CODE)**

`TELEGRAM_HOME_CHANNEL` in `~/.hermes/.env` — set by the `hermes gateway setup` "home channel" prompt,
and the canonical source the agent itself uses for unsolicited sends
(`tools/send_message_tool.py:439-452`, `tools/environments/local.py:279`).
Fallback if empty: the first id in `TELEGRAM_ALLOWED_USERS` (a private-chat user id is a valid `chat_id`).

→ **The P3 watchdog is implementable.** Read `TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL`, `curl` the
Telegram API directly. **NOT-RUN:** confirm the variable is actually populated after a real
`hermes setup` (`cut -d= -f1 ~/.hermes/.env` — key names only, never values).

---

## A4 — D1 needs no pip → **PASS (MEASURED)**

Run with Apple's system interpreter, not Homebrew's, to avoid a falsely optimistic result:

```
/usr/bin/python3 --version   → Python 3.9.6
```

| Test | Result |
|---|---|
| `test_check_topic_config.py` | PASS |
| `test_collect_sources.py` | PASS |
| `test_history.py` | PASS |
| `test_prepare_config.py` | PASS |
| `test_validate_report.py` | PASS |

All 5 pass on stdlib-only Python 3.9.6 → D1 needs no pip, and is compatible with the oldest interpreter
a customer Mac is likely to have. (This machine has Xcode CLT installed, so `/usr/bin/python3` resolved
without a dialog. **NOT-RUN:** on a clean Mac `/usr/bin/python3` triggers the CLT install prompt —
preflight must handle it.)
`generate_audio_file.py` without ffmpeg: **NOT-RUN**.

---

## P4/4.2 — which interpreter runs skill scripts → **ANSWERED (VERIFIED-BY-CODE)**

The plist `PATH` is built by `_build_service_path_dirs()` (`gateway.py:2791`) and is
`<install>/venv/bin : <node dirs> : <the user's full shell PATH>` (`gateway.py:4196`).
`<install>` = `~/.hermes/hermes-agent`. Skill docs invoke bare `python3`
(`skills/morning-report/SKILL.md:76`, `skills/doc-convert/SKILL.md:19`), resolved through that PATH.

→ **`python3` inside a skill = the Hermes venv python.** So P4's `~/.hermes/venv-docconvert` would be
invisible to the skill. **Install the doc-convert pip deps into the Hermes venv**
(`~/.hermes/hermes-agent/venv/bin/python -m pip install …`) — no wrapper needed.

Caveat to document: `hermes update` may rebuild that venv and drop the deps. `install-doc-addon.sh` must
stay re-runnable, and the healthcheck should run `preflight.py --compact` so the loss is detected.
**NOT-RUN:** confirm the venv path and that `preflight.py` passes under it.

### That venv has no pip (VERIFIED-BY-CODE) — `install.sh:setup_venv`

On macOS the venv is created with `$UV_CMD venv venv --python "$PYTHON_VERSION"` — **no `--seed`** — and
populated with `uv pip install`, never with `python -m pip`. A `uv venv` without seeding contains no pip
module at all, so the obvious `"$py" -m pip install python-docx …` fails with *No module named pip* on
every run. The add-on would fail forever, silently isolated by the step-10 trap.

uv itself is Hermes-managed at **`~/.hermes/bin/uv`** (`install.sh:install_uv`, `UV_UNMANAGED_INSTALL`).
`install-doc-addon.sh` therefore tries, in order: pip if it exists → `uv pip install --python <py>` →
`ensurepip` then pip.

---

## Sleep defaults → **MEASURED**

`pmset -g` on this Mac: `sleep 1`, `disksleep 10`, `displaysleep 15`, `womp 0`, `powernap 1`
(currently `sleep prevented by sharingd, caffeinate, powerd`).

→ Sleep **is** enabled by default; `sudo pmset -a sleep 0 disksleep 0` (P3 3.2) is mandatory. Note that
`pmset -g` reports *effective* settings including transient assertions, so the healthcheck should read
`pmset -g custom` (or `-c`) rather than trusting the "currently in use" block.

---

## Still NOT-RUN (needs a real machine and/or real accounts)

| # | Item | Command / action |
|---|---|---|
| A1-live | bootstrap succeeds; exactly 1 PID | `hermes gateway install`; `launchctl print gui/$UID/ai.hermes.gateway`; `pgrep -f "hermes gateway"` |
| A2-live | past-grace job runs once, late | delivery time 3 h in the past → restart gateway → expect one delivery |
| A3 | logout → login → gateway returns | log out, log in, `pgrep -f "hermes gateway"` |
| A5 | `hermes setup` screens on macOS | run it, capture every screen for the P2 guide |
| A7 | Firecrawl free tier: 1,000/month or lifetime? | sign up, read dashboard, measure credits before/after one report |
| — | `hermes update` leaves the service down? | `hermes update`, then `pgrep` |
| — | clean-Mac CLT dialog on `/usr/bin/python3` | fresh user / VM |
| — | total install time from clean | stopwatch |
| — | `generate_audio_file.py` without ffmpeg | run it |
| — | **No plaintext key in `~/hermes-install.log`** — our own output is masked, but the customer pastes the DeepSeek key and bot token *into `hermes setup`*, and whether that wizard echoes them back is A5, unmeasured. Mitigated by sending the wizard's output straight to `/dev/tty` instead of through `tee`; still needs proving | after a real install: `grep -c "<the pasted key>" ~/hermes-install.log` → must be 0 |
| — | Which launchd domain the agent actually lands in (`gui/$UID` vs `user/$UID`) | `launchctl print gui/$UID/ai.hermes.gateway`, then the same for `user/$UID` |
| — | doc-convert packages install into a real Hermes venv (the pip-less `uv venv` path) | run `install-doc-addon.sh` on a machine with Hermes installed |

---

## Changes this report forces on the plan

| Where | Change |
|---|---|
| `plan.md` limitation #2 | launchd bugs are already handled upstream (bootout+retry, detached fallback). Remaining risk is `hermes update`, covered by the watchdog |
| `plan.md` limitation #5 | late login → report arrives **late**, not lost |
| `phase-03` 3.1 steps 2–3 | **delete** — no `load -w` fallback, no `KeepAlive` patch (already `true`, self-heal reverts edits) |
| `phase-03` 3.4 | healthcheck should read `pmset -g custom`, not `pmset -g` |
| `phase-02` step 1 | pipe `install.sh` **only if `command -v hermes` fails** (A8 → 409 risk) |
| `phase-04` 4.2 | install deps into the **Hermes venv**, drop `venv-docconvert`; that venv has no pip, so go through `~/.hermes/bin/uv` |
| `phase-03` 3.3 | install the watchdog **after** the acceptance test, and never let it call a machine-level problem (`machine_can_sleep`) "the bot is not working" — otherwise it alerts the customer mid-install |
| `phase-03` 3.1/3.4 | probe both launchd domains (`gui/$UID`, then `user/$UID`) instead of hardcoding gui — upstream `_launchd_domain()` does |
| **new** | fix the cron-timezone bug (A6) — blocks P2 acceptance |

## Unresolved questions

1. **A6 fix: option A, B, or C?** (A recommended — touches shared D1 code + its test, no VPS regression.)
2. Install Hermes on this Mac to close the NOT-RUN runtime items? Needs consent (writes `~/.hermes`,
   `~/.zshrc`, clones the install tree) — and the key-dependent items (A5, A7) still need real accounts.
3. A7 (Firecrawl monthly vs lifetime) can only be answered by signing up — who does that, and when?
