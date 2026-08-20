---
phase: 2
title: "Installer + English wizard"
status: implemented
priority: P1
effort: "1-2d"
dependencies: [1]
---

# Phase 2: Installer + English wizard

> **Implemented.** `setup/install-mac.sh` (10 steps), `setup/lib/wizard-prompts.sh`,
> `setup/lib/validate-api-keys.sh`. Changes forced by the P1 report:
>
> - **Step 1 now only pipes the Hermes `install.sh` when `hermes` is absent** (A8). The
>   Hermes installer always runs its own gateway prompt and, on macOS, the yes-branch
>   starts `nohup hermes gateway` — a second long-poller. On a first install `.env` has
>   no token so the prompt never appears; on a re-run we skip the installer entirely.
>   This is also what makes the "Ctrl+C then re-run" criterion safe.
> - **Cron timezone fixed before acceptance could pass** (A6). `prepare_config.py`
>   emitted UTC; Hermes reads schedules in its own timezone. Uncaught, step 9's test
>   delivery would have failed by the UTC offset.
> - The installer keeps a copy of the source at `~/.hermes/morning-report-src`, so the
>   watchdog's health check and the re-runnable add-on do not break when the operator
>   deletes the folder they ran the installer from.
> - Steps are numbered "Step N of 10" in customer-facing output; internally the wizard
>   is step 3 and `hermes setup` step 4.
>
> - **The log-has-no-plaintext-keys criterion is only half provable here.** Our own output
>   masks keys, but the customer pastes the DeepSeek key and bot token into `hermes setup`,
>   whose echo behaviour is A5 (NOT-RUN). Mitigation: that wizard's output now goes straight
>   to `/dev/tty` instead of through `tee`, so it cannot reach the log at all. Proving it
>   still requires one `grep` against a real install — it is in the NOT-RUN table.
>
> Verified offline (`setup/tests/smoke-test-installer.sh`, 24 assertions): env round-trip
> with sed metacharacters, 0600 permissions, no duplicate keys, masking, all 5 validators
> rejecting bad keys against the live endpoints (all answer 401; Brave 422), generated
> artifacts parse as bash/plist. **Not run:** a real install on a Mac.

## Overview

One script, one line pasted into Terminal. **Both skills end up installed**: D1 (morning-report) directly, then D2 (doc-convert) via `install-doc-addon.sh`, which this script **chains automatically** at step 10 — the customer never has to remember a second command. The split exists only for failure isolation (P4), not to make D2 optional. No `config.env` generated. Copies skills instead of symlinking.

**Context:** Mac Studio / Mac mini, always on. Plenty of disk and CPU → no need to optimize for lightness at all costs; optimize for **install once, never touch again**.

All output, prompts, and code comments are **English only**.

## Why one Terminal line, not a double-clickable `.command`

A `.command` downloaded via browser or email carries `com.apple.quarantine` → "unidentified developer" dialog, and right-click → Open is not obvious. The executable bit is also lost through some zip/email paths. Pasting one line into Terminal carries **no quarantine at all**. Trade-off: the customer has to open Terminal — guide it with screenshots (Spotlight → type "Terminal").

```
curl -fsSL https://<host>/install-mac.sh | bash
```

## Requirements

**Functional**
- Runs on macOS Intel + Apple Silicon, macOS 13+.
- Idempotent: re-running after a mid-way failure doesn't re-ask for anything already stored (read `~/.hermes/.env` before prompting).
- Every prompt in English, each key accompanied by a signup link and validated on the spot.
- Logs to `~/hermes-install.log` (via `tee`), prints one line telling the customer to send that file to support if anything fails.
- Finishes with **a real report delivered through the real cron path**, not `ok:true`.

**Non-functional**
- No Homebrew, no pip, no LibreOffice in this script (D1 uses Python stdlib + curl only — confirmed in P1/A4). Those heavy deps belong to `install-doc-addon.sh` in P4.

## Architecture

```
install-mac.sh
 ├─ 0. preflight    macOS? version? arch? python3? free disk? network?
 ├─ 1. hermes CLI   curl install.sh | bash -s -- --skip-setup   (we drive setup ourselves)
 ├─ 2. wizard       Telegram token → DeepSeek key → Exa → Firecrawl → (Brave optional)
 │                   each step: signup link + paste + validate + retry
 ├─ 3. hermes setup run the native wizard (token + model key already in hand → guide the paste)
 ├─ 4. skills       COPY skills/morning-report → ~/.hermes/skills/productivity/
 ├─ 5. env          write EXA/FIRECRAWL/BRAVE into ~/.hermes/.env (mode 600)
 ├─ 6. gateway      call setup-launchd.sh (P3: LaunchAgent + KeepAlive + fallback load -w)
 ├─ 7. stability    sudo pmset -a sleep 0  +  call setup-watchdog.sh (P3)
 ├─ 8. configure MR prepare_config.py --save --enable-cron  (topics + delivery time, prompted)
 ├─ 9. acceptance   SET A TEMPORARY CRON 5 min out → wait → report arrives in Telegram on its own
 │                   → restore the real delivery time
 └─ 10. D2 add-on   run install-doc-addon.sh as a SUBPROCESS with failure trapped
                     → verify both skills present → .docx → .pptx round-trip
```

**Step 10 — both skills must end up installed.** `install-doc-addon.sh` is chained here, not merely suggested. It runs as a subprocess so `set -e` cannot propagate: if the add-on fails (brew, Xcode CLT, LibreOffice), the installer prints exactly what failed, tells the customer D1 is unaffected, and exits 0. The morning report never dies because of a document-conversion dependency.

**Step 1 — required syntax:** `bash -s -- --skip-setup`, not `bash --skip-setup` (the latter passes the flag to bash, not to the script — see `install.sh` line 12). P1 must also confirm: does `--skip-setup` suppress the gateway prompt too (`maybe_start_gateway`, ~line 2471)? If not, the customer hits an unexpected yes/no mid-install and **may install the gateway twice** — the 409 Telegram scenario arriving by accident.

**Step 9 — acceptance must go through the real delivery path.** Running `collect_sources.py` by hand only proves the API keys work; it proves **nothing** about whether the 8:00 cron fires and delivers — which is the entire product. The only test that covers it: schedule a temporary cron 5 minutes out via `prepare_config.py`, wait, confirm the report **arrives unattended**, then restore the real time. That exercises gateway alive → scheduler tick → skill run → TTS → Telegram send.

**Lock the topic count at step 8.** Customer capped it at **1–2 topics** → comfortably inside the Firecrawl free tier (1,000 credits/month, ~5–10 credits per report). Print a warning above 3 (exact number from P1/A7).

### Per-key validation (step 2)

| Key | Validation | Signup link shown to customer |
|---|---|---|
| Telegram bot token | `GET api.telegram.org/bot<TOKEN>/getMe` → print the bot name for the customer to confirm | @BotFather instructions |
| DeepSeek | cheapest possible request against the models endpoint | platform.deepseek.com |
| `EXA_API_KEY` | one test search | exa.ai |
| `FIRECRAWL_API_KEY` | one scrape of a static test URL | firecrawl.dev |
| `BRAVE_SEARCH_API_KEY` | optional, may be left blank | brave.com/search/api |

A bad key prints an English error and re-prompts **immediately** — never fail at 8am the next morning.

## Related Code Files

- Create: `setup/install-mac.sh` (main script, kept small — split helpers if it exceeds 200 lines)
- Create: `setup/lib/validate-api-keys.sh` (per-key validation)
- Create: `setup/lib/wizard-prompts.sh` (English prompts)
- Read for reference: `setup/scripts/03_setup_env_hermes.sh` (`set_env` — reuse), `setup/scripts/04_bootstrap_skill_hermes.sh` (switch symlink → copy)
- **Do not touch**: `setup/setup_all_hermes.sh` and `scripts/*` — leave the VPS path intact

## Implementation Steps

1. Skeleton `install-mac.sh` + `set -euo pipefail` + `tee ~/hermes-install.log` + trap that prints recovery instructions on failure.
2. Preflight: fail early if not macOS / `python3` missing (with `xcode-select --install` guidance) / free disk < 2GB.
3. Wizard + validation (two lib files).
4. Install Hermes CLI with `--skip-setup`, refresh PATH, `hash -r`.
5. Drive `hermes setup` — following the exact screens recorded in P1/A5; tell the customer up front what they'll be asked to paste.
6. Copy skills (`rsync -a --delete`) + `SOUL.md` if absent.
7. `prepare_config.py --save --enable-cron` with the topics + time the customer entered.
8. Acceptance: temporary cron 5 min out, wait, ask "did the report arrive in Telegram? [y/n]" → on n, print how to send the log.
9. Chain `install-doc-addon.sh` (P4) as a trapped subprocess, then verify both skills are present and working.

## Success Criteria

- [ ] On a fresh macOS user: one command → bot responds in Telegram, no action needed beyond pasting keys
- [ ] **Temporary cron 5 min out → report arrives on its own, unattended** (acceptance through the real delivery path)
- [ ] No unexpected prompts from `install.sh` mid-run; exactly one gateway installed
- [ ] Any bad key → English error on the spot, re-prompt, no abort
- [ ] `Ctrl+C` mid-run then re-run → does not re-ask for stored keys
- [ ] `~/hermes-install.log` has enough diagnostic detail and **contains no plaintext keys** (masked when logging)
- [ ] Deleting or moving the downloaded folder → skills still work (copied, not symlinked)
- [ ] No Homebrew/LibreOffice/pip installed by the D1 path (they belong to step 10)
- [ ] Choosing > 3 topics → prints a Firecrawl free-tier warning
- [ ] **After one run, both skills are installed**: `~/.hermes/skills/productivity/morning-report/` and `~/.hermes/skills/doc-convert/` both exist as real copies, `hermes doctor` sees both
- [ ] Add-on failure at step 10 → installer exits 0, states what failed, D1 still delivers

## Risk Assessment

- **`hermes setup` is an interactive wizard we don't control** → we cannot validate the DeepSeek key or bot token *inside* it. Mitigation: validate them in step 2 first, then have the customer paste the already-validated values; final acceptance is a real delivered report.
- **Customer gives up during the 4-API signup** (highest product risk). Mitigation: print the signup checklist **before** running the script so they collect all keys first.
- Keys leaking into the log → masking is mandatory.

## Security Considerations

- `~/.hermes/.env` chmod 600; `install-mac.sh` never writes keys to stdout or the log.
- No secrets hardcoded in the repo (`.gitignore` already covers this).
- Customer supplies their own keys → none of our secrets land on their machine.
