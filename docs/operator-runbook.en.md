# Operator Runbook

For the VPS administrator. End users do **not** need this document.

## Architecture overview

```
Telegram (users)
      │  long-polling (no public IP / webhook needed)
      ▼
Hermes Gateway  ── NATIVE install, systemd user service (hermes-gateway.service)
  ├─ LLM model: DeepSeek (DEEPSEEK_API_KEY in ~/.hermes/.env)
  ├─ Search (Morning Report skill): Exa primary + Brave fallback
  ├─ TTS: Google Translate endpoint (keyless) → MP3
  ├─ Tools: tts/web/browser/terminal… (hermes tools list)
  └─ Skills:
       • morning-report (D1): per-topic cron sends the morning brief
       • doc-convert   (D2): LibreOffice + python-docx/pptx/pypdf
```

**NATIVE install** (per this setup). Note: the official Hermes Docker image also includes the browser tool, but this setup uses native.

## Key file locations

| Item | Path |
|---|---|
| Secrets (tokens/keys) | `~/.hermes/.env` (mode 600) |
| Hermes config | `~/.hermes/config.yaml` |
| Skills | `~/.hermes/skills/` (symlinked from repo `openclaw-morning_report/skills/`) |
| Report history (per-topic, manifest.json/run) | `~/.hermes/skills/productivity/morning-report/state/history/` |
| Cron run output | `~/.hermes/cron/output/<job-id>/` |
| Gateway logs | `journalctl --user -u hermes-gateway.service` (or `hermes logs`) |
| Scripts + docs | `openclaw-morning_report/` directory (repo) |

> Hermes auto-loads `~/.hermes/.env` via `HERMES_HOME` — no manual env sourcing needed. The skill also loads `.env` on each run.

## Common operations

```bash
# Status + health
systemctl --user status hermes-gateway.service
hermes gateway status --deep
bash openclaw-morning_report/setup/scripts/healthcheck_hermes.sh   # prints JSON ok/problems

# Restart the gateway
hermes gateway restart

# Tail logs
journalctl --user -u hermes-gateway.service -f

# Morning-report cron (per-topic: "Morning Report - <topic>")
hermes cron list --all              # jobs + Last run + next run
hermes cron run <job-id>            # force run now (debug)
ls -t ~/.hermes/cron/output/<job-id>/ | head -1   # latest run output

# Health / audit
hermes doctor                       # "All checks passed" = clean
hermes security audit               # supply-chain (OSV.dev)
```

## Rotating an API key / token

1. Edit the value in `~/.hermes/.env` (nano, **no sudo** — user-owned file, mode 600).
   - Search keys (EXA/FIRECRAWL/BRAVE): the skill reloads `.env` each run → no restart needed.
   - Telegram/DeepSeek: restart the gateway (step 2).
2. `hermes gateway restart`
3. `hermes doctor` to confirm the setup is healthy.

Hermes stores secrets in `~/.hermes/.env` (mode 600); `config.yaml` holds no plaintext. Editing the value in `.env` is enough.

## Changing delivery time / timezone (per-topic)

Simplest: tell the bot *"Change [topic] to 7 AM"* (skill Update Config, per-topic).
CLI (via the skill, reconciles cron jobs):
```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py \
  --topic "<topic>" --delivery-time "07:00" --save --enable-cron
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot not responding | Gateway down / network | `hermes gateway restart`; check `journalctl --user -u hermes-gateway.service` |
| Sparse report, logs show `429` | Exa/Brave rate-limited | The skill auto-falls back Exa→Brave. If both 429: check `EXA_API_KEY`/`BRAVE_SEARCH_API_KEY` in `~/.hermes/.env`; retry later. (Platform web tool: `hermes config set web.search_backend` + `05_searxng_hermes.sh` optional) |
| Audio MP3 not sent | MEDIA path / Deliver / tts | `hermes tools list` (tts enabled by default). `hermes cron list --all` (Deliver: origin). MP3 is written by the skill to `~/.hermes/skills/.../state/history/<run>/` |
| `hermes doctor` reports an issue | Missing config/dep | `hermes doctor --fix` (try auto-fix) or read the output |
| Stranger's messages blocked | Pairing / allowed users | `hermes pairing approve <code>`; or set `TELEGRAM_ALLOWED_USERS` in `~/.hermes/.env` then `hermes gateway restart` |
| Bot silent after VPS reboot | Lingering not enabled | `sudo loginctl enable-linger <user>` |
| Cron reports "LLM request failed" | Run exceeded ~9 min and the stall watchdog aborted it (usually the `pro` reasoning model composing slowly + search 429) | Use the fast model as default: `hermes config set model deepseek/deepseek-v4-flash` + `hermes fallback add` (pick pro); and fix search 429. NOT a key/balance issue |

## Verifying "48h stability" (D3 AC)

1. Reboot the VPS → confirm the gateway comes back on its own: `systemctl --user is-active hermes-gateway.service` = active.
2. Monitor for 48h, check daily:
   - `hermes cron list --all` → each topic has a successful morning run (Last run: ok).
   - `~/.hermes/skills/productivity/morning-report/state/history/` has a fresh run (manifest.json by date).
   - `bash setup/scripts/healthcheck_hermes.sh` → `"ok":true`.
   - `hermes doctor` → All checks passed.
3. (Optional) schedule a cron (`hermes cron create`) to call `healthcheck_hermes.sh` every few hours and Telegram-alert the operator if `ok:false`.

## Google Workspace (D2)

- Credentials: `~/.hermes/skills/doc-convert/state/google-creds/` (symlink → repo) contains `client_secret.json` (OAuth desktop client) + `token.json` (refresh token, mode 600). The dir has `.gitignore='*'` so it never reaches a repo.
- First-time setup (create the project, enable APIs, **PUBLISH APP**, create the client, authorize, verify, troubleshoot): [google-oauth-setup.en.md](google-oauth-setup.en.md).
- Re-authorize (token broken / account change): `python3 ~/.hermes/skills/doc-convert/scripts/authorize_google.py --port 8765` (headless VPS: SSH-tunnel `ssh -L 8765:localhost:8765 <user>@<vps>`).
- Must be enabled in Google Cloud Console: **Drive API + Docs API + Slides API**. If the consent screen is in Testing mode, the account must be a listed Test user.
- Verify: `python3 ~/.hermes/skills/doc-convert/scripts/preflight.py --compact` → `google.authorized_token: true`.
- **Two scope sets** (`DOC_CONVERT_GOOGLE_SCOPES`), because scopes decide how hard customer setup is:
  - `minimal` — `drive.file` only. Covers the whole conversion pipeline (upload, export, Slides readback) because every file involved is one the app created. Non-sensitive scope: an OAuth client asking for nothing else publishes without verification, shows no "unverified app" screen, and its refresh tokens do not expire after 7 days. Customer setup = one consent click. Private Google links are refused with an actionable message.
  - `private-links` (default) — adds `drive.readonly` so pasted private Docs/Slides/Drive links work. RESTRICTED scope: publishing needs app verification plus an annual CASA assessment, so in practice each customer creates their own OAuth client.
  - The `documents` and `presentations` scopes were removed — the old Docs/Slides batchUpdate builders are gone and the readback works under `drive.file`.
  - `preflight.py` reports `scope_set_requested`, `granted_scopes` and `can_read_private_links`; the stored token's grant wins over whatever the code asks for, so an existing deployment keeps working after a default change.
- Capabilities: read **private** Docs/Slides/Drive (private-links only); render every conversion in Google.
- **Google is the renderer of record.** `convert.py` builds a .pptx/.docx locally, imports it into Slides/Docs, and exports the file the user asked for back out of Google — a python-pptx deck renders differently in PowerPoint for Mac, a Google one does not. Files are created private in the connected account's Drive; the run dir keeps the uploaded intermediate under `build/`.
- Targets: `gslides`/`gdoc` (link + exported PDF), `pptx`/`docx`/`pdf` (Google's export), `md` (local, never touches Google). `--no-google` forces local rendering for debugging.
- Without a token the skill still converts, but adds a `google_unauthorized:rendered_locally` warning and `gslides`/`gdoc` fail — check preflight first when a user reports a file that "looks wrong on Mac".
- Post-import check: `convert.py` reads the deck back through the Slides API (`google_check` in the manifest); re-run it with `validate_output.py --google <url>`.
- Drive refuses exports above **10 MB**: a photo-heavy deck then arrives as a link with a `google_export_failed:` warning and no PDF.

## Known limitations

- **Keyless TTS**: uses the unofficial Google Translate endpoint; may be blocked/changed without notice. Upgrade path: Google Cloud TTS (keyed) or `edge-tts`.
- **Slide imagery (D2)**: depends on the search provider; if search is throttled, slides may lack images.
- **OAuth client secret**: was pasted through chat during setup — rotate it in Google Cloud Console after handover.
