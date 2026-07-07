# Operator Runbook

For the VPS administrator. End users do **not** need this document.

## Architecture overview

```
Telegram (users)
      │  long-polling (no public IP / webhook needed)
      ▼
OpenClaw Gateway  ── NATIVE install, systemd user service, bind 127.0.0.1:18789
  ├─ LLM model: DeepSeek (key via SecretRef)
  ├─ Search: <provider> (Brave/Tavily/SearXNG…)
  ├─ TTS: Google Translate endpoint (keyless) → MP3
  ├─ browser tool (present ONLY with NATIVE install, not Docker)
  └─ Skills:
       • morning-report (D1): cron sends the morning brief
       • doc-convert   (D2): LibreOffice + python-docx/pptx/pypdf
```

**Install NATIVE, not Docker** — Docker strips OpenClaw's browser tool.

## Key file locations

| Item | Path |
|---|---|
| Secrets (tokens/keys) | `/etc/openclaw/openclaw.env` (mode 600) |
| Gateway config | `~/.openclaw/openclaw.json` |
| systemd drop-in loading env | `~/.config/systemd/user/openclaw-gateway.service.d/override.conf` |
| Workspace skills | `~/.openclaw/workspace/skills/` |
| Report history (run evidence) | `~/.openclaw/workspace/skills/morning-report/state/report-history/` |
| Skill audit log | `~/.openclaw/workspace/skills/morning-report/state/audit.log` |
| Gateway logs | `journalctl --user -u openclaw-gateway.service` |
| Scripts + docs | `morning-brief-setup/` directory |

> Every `openclaw` command needs env loaded: `set -a; . /etc/openclaw/openclaw.env; set +a`
> (Auto-load is already added to `~/.bashrc`, so a new terminal has it.)

## Common operations

```bash
# Status + health
systemctl --user status openclaw-gateway.service
openclaw gateway status
bash morning-brief-setup/scripts/healthcheck.sh     # prints JSON ok/problems

# Restart the gateway
systemctl --user restart openclaw-gateway.service

# Tail logs
journalctl --user -u openclaw-gateway.service -f

# Morning-report cron
openclaw cron list                 # jobs + next run
openclaw cron runs <job-id>        # run history
openclaw cron run <job-id>         # force run now (debug)

# Secrets
openclaw secrets audit --check     # must be: clean, plaintext=0
```

## Rotating an API key / token

1. Edit the value in `/etc/openclaw/openclaw.env` (nano, sudo).
2. `systemctl --user restart openclaw-gateway.service`
3. `openclaw secrets audit --check` to confirm it hasn't fallen back to plaintext.
Because config uses SecretRefs pointing at env vars, changing the env value is enough — no need to touch `openclaw.json`.

## Changing delivery time / timezone
Simplest: tell the bot *"Send the report at 7 AM"*. CLI: `openclaw cron edit <job-id>` (see `openclaw cron edit --help`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot not responding | Gateway down / network | `systemctl --user restart openclaw-gateway.service`; check logs |
| Sparse report, log shows `429 RATE_LIMITED` | Search provider (Brave free) throttled | Switch provider: set `OC_SEARCH_PROVIDER` + run `07_configure_integrations.sh`; or stand up SearXNG (`08_searxng.sh`) |
| No audio generated / MP3 won't send | Missing `tts`/`message` tool, or sending file from outside workspace | Run `07_configure_integrations.sh` (opens `tools.alsoAllow`); MP3 must live inside the workspace, never `/tmp` |
| `secrets audit` reports plaintext | New key not migrated | Re-run `05_migrate_secrets.sh` |
| Stranger's messages blocked | Pairing gate | `openclaw pairing approve telegram <code>` |
| Bot silent after VPS reboot | Lingering not enabled | `sudo loginctl enable-linger <user>` |
| Cron reports "LLM request failed" | Run exceeded ~9 min and the stall watchdog aborted it (usually the `pro` reasoning model composing slowly + search 429 dragging it out) | Use the fast model as default: `openclaw models set deepseek/deepseek-v4-flash` + `openclaw models fallbacks add deepseek/deepseek-v4-pro`; and fix search 429. NOT a key/balance issue (check `curl .../user/balance`) |

## Verifying "48h stability" (D3 acceptance)
1. Reboot the VPS → confirm the gateway comes back on its own: `systemctl --user is-active openclaw-gateway.service` = active.
2. Monitor for 48h, check daily:
   - `openclaw cron runs <job-id>` → a successful 7 AM run exists.
   - `report-history/` has a fresh dated folder.
   - `bash scripts/healthcheck.sh` → `"ok":true`.
   - `openclaw secrets audit --check` → clean.
3. (Optional) schedule an OpenClaw cron to call `healthcheck.sh` every few hours and Telegram-alert the operator if `ok:false`.

## Google Workspace (D2 — configured)
- Credentials live in `~/.openclaw/workspace/skills/doc-convert/state/google-creds/`: `client_secret.json` (OAuth desktop client) + `token.json` (refresh token, mode 600). The dir has `.gitignore='*'` so it never reaches a repo/bundle.
- Re-authorize (token broken / account change): `python3 skills/doc-convert/scripts/authorize_google.py --port 8765` (headless VPS: SSH-tunnel `ssh -L 8765:localhost:8765 <user>@<vps>`).
- Must be enabled in Google Cloud Console: **Drive API + Docs API + Slides API**. If the consent screen is in Testing mode, the account must be a listed Test user.
- Verify: `python3 skills/doc-convert/scripts/preflight.py --compact` → `google.authorized_token: true`.
- Capabilities: read **private** Docs/Slides/Drive; create drafts directly in Google Docs (`--to gdoc`) / Slides (`--to gslides`).

## Known limitations
- **Keyless TTS**: uses the unofficial Google Translate endpoint; may be blocked/changed without notice. Upgrade path: Google Cloud TTS (keyed) or `edge-tts`.
- **Slide imagery (D2)**: depends on the search provider; if search is throttled, slides may lack images.
- **OAuth client secret**: was pasted through chat during setup — rotate it in Google Cloud Console after handover.
