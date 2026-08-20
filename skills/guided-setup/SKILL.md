---
name: guided-setup
description: Use when the user needs to set up, connect, reconnect or repair the assistant itself — first-time setup, "cài đặt giúp tôi", missing or expired API keys (Exa, Firecrawl, Brave), connecting Google for Slides/Docs output, or errors that say a key is missing, invalid, unauthorized, or that Google is not connected. Walks a non-technical user through creating each key, saves what they paste, and proves the result works.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [setup, onboarding, api-keys, google-oauth, troubleshooting]
    related_skills: [morning-report, doc-convert]
---

# Guided Setup

Connects the two skills to the services they need — **Morning Report** (news search) and
**Document Conversion** (Google Slides/Docs output) — entirely through chat. The user
creates each key in their own browser and pastes it here; the scripts clean, verify and
store it in `~/.hermes/.env` (mode 600) and in the Google credentials directory.

## Who this is written for

Assume the user has never seen a terminal, is on a phone, and will abandon the setup if
a message looks like documentation. That assumption drives every rule below.

**How to talk during setup**

- One item at a time. Never list all four services in one message.
- Per item: say what it is for in one sentence, then send the link, then the numbered
  clicks (max ~5 short steps), then stop and wait for the paste.
- Send links as plain URLs on their own line so they stay tappable.
- Never show the user JSON, flags, file paths, or script names. They asked for help, not
  a log.
- Never echo a key back, not even partially masked, unless the user asks which key is
  stored. Secrets do not belong in chat history.
- Free tiers are enough for all three keys. Say so — cost is the most common reason
  people stop here.
- If the user says they will do it later, save what exists, tell them exactly what still
  works and what does not, and offer to continue any time by saying "tiếp tục cài đặt".

## Workflow Router

- **First-time setup, "cài đặt giúp tôi", "setup for me":** → [First-Time Setup](#first-time-setup)
- **Add or replace one key (Exa / Firecrawl / Brave):** → [Connect One Key](#connect-one-key)
- **Connect or reconnect Google:** → [Connect Google](#connect-google)
- **"Why is this broken", a key error, or a status question:** → [Check And Repair](#check-and-repair)

---

## First-Time Setup

Run the whole sequence, but stop between steps and let the user answer. Skipping ahead
because "it will probably work" is what produces a bot that fails at 6am on day one.

### Step 1: See what is already connected

```bash
python3 ~/.hermes/skills/guided-setup/scripts/check_setup.py
```

Read `ready`, `missing`, `next_step` and `warnings`. Tell the user in one short list what
is connected and what is not, then say how long the rest takes (about 10 minutes for the
three keys, 10 more for Google).

Ask which they want now:

- **Morning Report only** → Steps 2–3, then Step 5.
- **Everything** → Steps 2–5.

### Step 2: Collect the search keys

Work through `missing` in the order `check_setup.py` gives (`exa`, `firecrawl`, `brave`),
using [Connect One Key](#connect-one-key) for each. Exa first: without a search key
Morning Report cannot run at all, while the other two only make it better.

### Step 3: Configure the report itself

Once at least one search key is verified, hand off:

> Load `skill_view(name="morning-report")` and follow its **Update Config** workflow.

That workflow asks for topics, delivery time, timezone, style, language and audio, and
saves the cron job. Come back here afterwards.

### Step 4: Connect Google (only for Document Conversion)

Follow [Connect Google](#connect-google). Say plainly what skipping costs: conversions
still work but files are built on the server, which can look wrong when opened in
PowerPoint on a Mac, and "send it as Google Slides" will fail. Mention the one benefit
that ties the two features together: with Google connected, any morning report they
receive can be turned into a Google Doc or a slide deck just by asking — no file to
send back.

### Step 5: Prove it works

Two real runs, not a claim:

1. Morning Report: run the morning-report skill's **Run Report** workflow once and
   deliver the result.
2. Document Conversion (only if Google was connected):
   ```bash
   python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py test
   ```
   Send `google_url` as a clickable link and tell the user the file is private in their
   own Drive and safe to delete.

Finish by telling the user what they can say next: run the report, change topics, pause
it, or send a file to convert.

---

## Connect One Key

Use for `exa`, `firecrawl` and `brave`, one at a time.

### Step 1: Send the instructions for that key

Read the section for the key in
`~/.hermes/skills/guided-setup/references/key-guides.vi.md` (Vietnamese) or
`key-guides.en.md` (English) and relay it as short numbered steps in the user's language.
Do not paste the reference file as-is and do not skip the "what it looks like" line — it
is what stops the user pasting the wrong string.

### Step 2: Save what the user pasted

Pass the user's message through verbatim; the script strips quotes, labels and stray
lines, verifies the key with the provider and only then stores it.

**Feed it on stdin, with a quoted heredoc.** What the user pasted can contain quotes,
`$`, backticks or `&`, and as a shell argument any of those changes or truncates the
value before the script ever sees it:

```bash
python3 ~/.hermes/skills/guided-setup/scripts/save_key.py --name exa <<'PASTE'
<what the user pasted, exactly as they sent it>
PASTE
```

`--value "<...>"` also works and is fine for a value you can see is plain, but stdin is
the default choice.

Read the JSON and follow `next_action`:

- `success: true` → confirm in one line, then move to the next item.
- `problems` non-empty → the message was not a key. Tell the user which mistake it was,
  in their language, and ask again. Do not save it anyway.
- `verify.state: "rejected"` → the provider refused the key. Ask them to check they
  copied all of it, or to create a new one.
- `verify.state: "unverified"` → the key is stored but the provider could not be reached.
  Say so, and re-check later with `check_setup.py --verify`.

Only pass `--force` if the user explicitly insists after being told the key looked wrong.

---

## Connect Google

Roughly 10 minutes, all in the user's browser plus two pastes into this chat. Full
click-by-click text is in the `## Google` section of
`~/.hermes/skills/guided-setup/references/key-guides.vi.md` (or `.en.md`); the reasoning
behind each screen is in the repo's `docs/google-oauth-setup.vi.md`.

**Ask first, once:** does the user want the bot to be able to open *private* Google
Docs/Slides links they paste into chat?

- **No** (default, recommended) → `minimal`. The bot only ever touches files it created
  itself, and Google shows no warning screen.
- **Yes** → `private-links`. The bot can read files the user has access to, and the user
  will have to click through a "Google hasn't verified this app" screen.

### Step 1: The user creates the app in Google Cloud

Relay the console steps from the reference. Two of them decide whether this setup
survives:

- **Publish the app.** Left in *Testing*, Google expires the connection after exactly 7
  days and the bot breaks a week later with no visible cause.
- **Application type: Desktop app.** A *Web application* client fails at the last step
  with `redirect_uri_mismatch`.

### Step 2: Store the app's credentials

The user can either send the downloaded JSON file, or copy the client ID and secret off
the screen:

```bash
# they sent the file (use the path Telegram saved it to)
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py client --file "<path>"

# they pasted the file contents — heredoc, so the braces and quotes survive
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py client <<'PASTE'
<the JSON they pasted>
PASTE

# they pasted the two values
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py client \
  --client-id "<...apps.googleusercontent.com>" --client-secret "<...>"
```

Add `--scopes private-links` here (or on `start`) if the user chose private links.

### Step 3: Send the consent link

```bash
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py start
```

Send `auth_url` on its own line, then tell the user, in this order:

1. Open the link and pick the Google account whose Drive should hold the files.
2. Press **Allow** (with `private-links`: **Advanced → Go to … (unsafe)** first).
3. The browser will land on an error page — *"This site can't be reached"*. **That is
   the expected result**, not a failure. Say this before they see it, or they will
   report it as a problem.
4. Copy the **whole address** from the address bar and paste it into the chat.

### Step 4: Finish the connection

```bash
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py finish <<'PASTE'
<the address they copied out of the browser>
PASTE
```

The address is full of `&` and `?`, so pass it on stdin like this rather than as
`--redirect-url`; a stray `&` cuts the code in half and produces a confusing failure.

On success, tell the user which Google account got connected (`account`) and ask them to
confirm it is the right one — every file the bot creates lands in that account's Drive.
On failure, `next_action` already carries the fix; relay it in the user's language.

### Step 5: Prove it

```bash
python3 ~/.hermes/skills/guided-setup/scripts/google_setup.py test
```

`success: true` with `render_engine: "google"` is the only pass. Anything else: tell the
user it did not work and what the warning says. Never claim Google works without this.

---

## Check And Repair

Use for "is it set up?", "why did the report fail?", "the bot says it can't read my
Google link", or any error that mentions a key.

### Step 1: Check with live verification

```bash
python3 ~/.hermes/skills/guided-setup/scripts/check_setup.py --verify
```

`--verify` calls each provider, so it catches the failures presence checks miss: a
deleted key, an exhausted free quota, a revoked Google access.

### Step 2: Read the result and act

| What you see | What it means | What to do |
| --- | --- | --- |
| `keys[].status: "invalid"` | Provider rejected the stored key | [Connect One Key](#connect-one-key) again for that key |
| `keys[].status: "unverified"` | Provider unreachable from the server | Not the user's fault; retry later, tell the operator if it persists |
| `ready.morning_report: false` | No working search key | Connect Exa (or Brave) before anything else |
| `google.status: "client_only"` | App registered, nobody pressed Allow | [Connect Google](#connect-google) from Step 3 |
| `google.status: "missing"` | No Google at all | Conversions still work, rendered locally — say so |
| `google.can_read_private_links: false` + user pasted a private link | Connected with `minimal` | Offer either uploading the file directly, or reconnecting with `--scopes private-links` |
| `warnings` contains `gcreds_env_not_exported` | Credentials path lives only in `.env` | Already handled by a symlink; mention it only to an operator |

Reconnecting Google after a revoke or an account change is the same flow from Step 2 of
[Connect Google](#connect-google); the old token is overwritten.

---

## Guardrails

- Never invent a key, a URL or a console screen. If a provider's page has changed and
  the reference no longer matches, say so and ask the user to describe what they see.
- Never write a key to a file yourself; `save_key.py` and `google_setup.py` own
  `~/.hermes/.env` and the credentials directory, and they set the file modes.
- Never say setup is complete without the proofs in Step 5 — `check_setup.py --verify`
  for keys, `google_setup.py test` for Google.
- The Telegram bot token and the model key are not part of this skill: they were set by
  the installer before this conversation could exist. If they are the problem, the
  operator has to fix them on the server (`docs/operator-runbook.vi.md`).
- If the user offers a password, a credit card number, or the login of their Google
  account, refuse and explain that none of it is ever needed — only the keys and the one
  Allow button.
- After Google is connected, tell the user once that the message containing the client
  secret (or the JSON file) is still sitting in this chat, and suggest deleting it. It is
  their secret and their chat history; say it plainly instead of leaving it there quietly.
