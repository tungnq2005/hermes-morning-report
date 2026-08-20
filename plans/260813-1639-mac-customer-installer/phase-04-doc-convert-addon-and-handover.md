---
phase: 4
title: "doc-convert add-on + handover docs"
status: implemented
priority: P1
effort: "0.5-1d"
dependencies: [2]
---

# Phase 4: doc-convert add-on + handover docs

> **Implemented:** `setup/install-doc-addon.sh`, `docs/install-mac.md`,
> `docs/limits-mac.md`, `docs/troubleshoot-mac.md`, plus macOS sections in `README.md`
> and `setup/README.md` (existing Vietnamese VPS content untouched).
>
> **4.2 changed — no `venv-docconvert`.** The open question ("which python does Hermes
> invoke for skill scripts?") is answered: the gateway plist puts `<install>/venv/bin`
> first on PATH and skills call bare `python3`, so a skill's `python3` **is the Hermes
> venv python**. A separate venv would have left the packages installed but invisible.
> `resolve_skill_python()` reads `VIRTUAL_ENV` out of the gateway plist, falls back to
> `~/.hermes/hermes-agent/venv/bin/python3`, then to system `python3` with a warning.
> Documented consequence: `hermes update` can rebuild that venv and drop the packages —
> hence the add-on is re-runnable and `troubleshoot-mac.md` §5 says to re-run it.
>
> **That venv has no pip.** `install.sh:setup_venv` runs `uv venv` without `--seed` and fills
> it with `uv pip install`, so `python -m pip` does not exist there — the obvious
> `"$py" -m pip install python-docx …` would fail on every machine. The add-on tries pip,
> then Hermes' own uv at `~/.hermes/bin/uv` (`uv pip install --python <py>`), then `ensurepip`.
>
> Also: the add-on installs **ffmpeg** too (audio joining falls back to raw concat
> without it), and `rsync` for D2 deliberately omits `--delete` so `state/` (Google
> credentials, output history) survives a re-run.
>
> **Not run:** the `.docx` → `.pptx` round-trip and `preflight.py --compact` on macOS —
> both need LibreOffice + the pip packages, which is what the add-on installs.
> `skills/doc-convert/tests/test_convert.py` cannot run on a machine without
> `python-pptx` (pre-existing, unchanged by this work).

## Overview

**Both skills ship.** D1 (morning-report) and D2 (doc-convert) are both part of standard handover — a machine that finishes install has both working. D2 lives in its own script, but `install-mac.sh` chains into it automatically so the customer never has to remember a second step.

## Why a separate script even though both are mandatory

**Failure isolation**, not disk savings (the Mac Studio has plenty). D1 needs Python stdlib + `curl` — present on macOS, nearly unbreakable. D2 pulls in Homebrew + Xcode CLT + the LibreOffice cask + 7 pip packages = 4 new failure points. Merged: brew fails → `set -e` → **the morning report dies too**. Split: D2 fails, D1 keeps running, fix D2 afterwards.

`install-mac.sh` step 10 runs `install-doc-addon.sh` as a **subprocess with its failure trapped** — never inheriting `set -e` into the D1 path. If the add-on fails, the installer reports exactly that and exits 0 with D1 working.

Handover flow: run `install-mac.sh` → accept the morning report → add-on runs automatically → accept document conversion.

## Requirements

- Functional: `install-doc-addon.sh` runs standalone (re-runnable after a failure) and is also chained from `install-mac.sh`.
- Functional: `soffice` resolvable from PATH.
- Functional: at the end, **both** skills are present and verified — not just installed.

## Architecture

### 4.1 The `soffice` trap on macOS

`skills/doc-convert/scripts/convert.py:163` calls `["soffice", ...]` — a bare name resolved via PATH. The LibreOffice cask does **not** put `soffice` on PATH. The add-on must:

```
ln -sf /Applications/LibreOffice.app/Contents/MacOS/soffice <prefix>/bin/soffice
```

`<prefix>` = `/opt/homebrew` (Apple Silicon) or `/usr/local` (Intel) — detect via `brew --prefix`. Confirm with `skills/doc-convert/scripts/preflight.py --compact` (it already checks `soffice` as required).

### 4.2 Python deps

Ubuntu uses `pip3 install --break-system-packages`. On macOS use a dedicated venv at `~/.hermes/venv-docconvert`, leaving system Python untouched. Must confirm doc-convert scripts actually run from that venv — **which `python3` does Hermes invoke for skill scripts?** If Hermes calls system `python3`, install into that interpreter instead, or add a wrapper. Verify, don't assume.

### 4.3 Both-skills verification

Neither skill is "installed" until proven. At the end of the chained run:

```
~/.hermes/skills/productivity/morning-report/   exists, is a real copy (not a symlink)
~/.hermes/skills/doc-convert/                   exists, is a real copy
python3 .../doc-convert/scripts/preflight.py --compact   → pass
hermes doctor                                            → skills detected, clean
```

Plus the two live acceptance tests: a report delivered by the real cron path (P2 step 9), and a `.docx` → `.pptx` round-trip through the bot.

### 4.4 Handover docs (English)

Short, plain English, written for someone who is not technical:

| File | Contents |
|---|---|
| `docs/install-mac.md` | Checklist of the 4 API signups to complete **before** installing (links + screenshots) → paste one line → paste keys → add-on runs automatically. Includes every macOS dialog they'll see + **the real API cost table** (from P1/A7) |
| `docs/limits-mac.md` | One page, the 11 limitations from `plan.md`. Bold at the top: **the machine must stay on and logged in**; after a reboot someone must log in again before the bot runs; logging in more than 2h after delivery time loses that day's report — message the bot "send report" to fetch it manually. Explicitly lists what is **out of scope**: power outages, auto-login, remote access |
| `docs/troubleshoot-mac.md` | 5 common failures + how to run `hermes-check` + how to send `~/hermes-install.log` + what the watchdog alert means. **Critical because there is no remote access** — every diagnosis happens through the block the customer pastes back |

**Language scope:** all new files here are English. In `README.md` / `setup/README.md`, write the **new macOS sections in English** and leave the existing Vietnamese VPS sections untouched — a mixed-language README is acceptable; rewriting the whole repo is out of scope. The pre-existing `docs/user-guide.vi.md`, `docs/operator-runbook.vi.md`, `docs/chat-commands.md` are not modified.

Update `README.md` + `setup/README.md`: clearly separate the two paths — **VPS Ubuntu** (`setup_all_hermes.sh`) vs **always-on macOS desktop** (`install-mac.sh`, which chains `install-doc-addon.sh`). Neither is the default "recommended" one: VPS is more reliable, macOS reuses hardware the customer already owns with no hosting fee.

## Related Code Files

- Create: `setup/install-doc-addon.sh`
- Create: `docs/install-mac.md`, `docs/limits-mac.md`, `docs/troubleshoot-mac.md`
- Modify: `setup/install-mac.sh` (chain the add-on with failure trapped), `README.md`, `setup/README.md`
- Read: `skills/doc-convert/scripts/preflight.py`, `convert.py:163`

## Implementation Steps

1. `install-doc-addon.sh`: verify D1 is installed → brew (install if missing; ask first, it needs sudo + CLT) → cask libreoffice → symlink `soffice` → venv + pip deps → COPY `skills/doc-convert` into `~/.hermes/skills/` → `preflight.py --compact` must pass.
2. Confirm which interpreter Hermes uses for skill scripts; align the venv or add a wrapper (4.2).
3. Chain it from `install-mac.sh` step 10 with failure trapped, then run the 4.3 verification block.
4. Write the three English docs.
5. Update both READMEs to separate the two install paths.
6. (Optional) `authorize_google.py` — OAuth needs a browser; document separately, don't automate.

## Success Criteria

- [ ] **After one `install-mac.sh` run, both skills are installed and verified** (4.3 block passes)
- [ ] Send a `.docx` to the bot → receive a `.pptx`
- [ ] `preflight.py --compact` passes on macOS
- [ ] Add-on fails mid-way → D1 (morning report) still works, installer exits 0 and says exactly what failed
- [ ] `install-doc-addon.sh` is re-runnable standalone after a failure
- [ ] Customer reads `limits-mac.md` and understands the constraints without further explanation
- [ ] READMEs clearly distinguish the VPS path from the macOS path

## Risk Assessment

- **Homebrew needs Xcode CLT (~2GB+) and sudo** → slow download with dialogs. Mitigation: run the add-on during the live handover session rather than leaving it to the customer.
- **Hermes may call a different Python than the venv** → deps "installed" but the skill can't see them. Must be verified in step 2, never assumed.
- Google OAuth needs a browser + a Google Cloud project → almost certainly done on the customer's behalf. The always-on machine keeps token refresh stable, but refresh tokens can still expire; cover it in troubleshooting.
- **Customer doesn't understand the scope limits** → reboots, doesn't log in, assumes the bot is broken, calls support. Mitigation: `limits-mac.md` leads with "machine must stay on and logged in"; read it together during handover.
