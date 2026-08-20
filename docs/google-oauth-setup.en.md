# Connecting Google Workspace for Document Conversion

There are **two routes** to the same result:

| | **Route A — in chat** (default) | **Route B — terminal** |
| --- | --- | --- |
| Who does it | **the end user**, on their own | the installer |
| Needs | Telegram + a browser | SSH to the VPS + an SSH tunnel |
| Say / run | *"Connect Google for me"* | `bash setup/scripts/06_google_oauth_hermes.sh` |
| Who holds `client_secret.json` | nobody has to hand it over — it goes straight to the server | the installer holds the customer's file and `scp`s it up |

**Route A is the right one when the Drive belongs to the customer**: they press Allow
themselves and you never handle their secret. The `guided-setup` skill narrates every
console screen, takes what they paste in chat, and replaces the SSH tunnel with a simple
trick — see [Step 7](#7-install-it-on-the-server-and-authorize-once).

This guide explains **why** each screen matters, so it is written for the **installer**
and for looking things up when something breaks. End users only need
[first-run-setup.en.md](first-run-setup.en.md).

Budget about **15 minutes**. One step is skipped by nearly everyone and it breaks the bot
exactly seven days later — Step 5. Do not skip it.

---

## 1. Why this is needed

The bot builds its results in Google before handing them over. A .pptx produced on a
server does not draw the same way in PowerPoint for Windows and PowerPoint for Mac —
fonts, spacing and layout shift — while a Google Slides file looks **identical** on macOS,
Windows, iPad and in a browser. Every .pptx/.docx/.pdf handed back to the user is
**exported from that same Google file**, so the result no longer depends on the viewer's
machine.

To do that, the bot needs permission to create files in **the user's** Google Drive. That
permission comes from OAuth — the same "Sign in with Google" flow you already know.

Without Google the bot still runs: it renders locally and records a
`google_unauthorized:rendered_locally` warning in the manifest. But that is exactly the
kind of file that renders wrong on a Mac, and `--to gslides` / `--to gdoc` fail outright.

---

## 2. Choose the scope set first

This is the decision that matters most: it changes both the install and the user's
experience.

| | `minimal` | `private-links` (default) |
| --- | --- | --- |
| Scopes requested | `drive.file` | `drive.file` + `drive.readonly` |
| What the bot can see in Drive | **Only files it created itself** | Every file the user can read |
| Reads private Docs/Slides links the user pastes | No | Yes |
| Google's classification | Non-sensitive | **Restricted** |
| "Google hasn't verified this app" screen | Never shown | Shown; user clicks Advanced → Continue |
| To publish widely | No review needed | App verification + annual CASA assessment |
| Refresh token expires after 7 days? | No, **provided** Step 5 is done | No, **provided** Step 5 is done |

**Pick `minimal`** when users mostly send files straight into Telegram. It is the
cleanest option: no warning screen, the narrowest possible permission, and an easy
sentence for the customer — "the bot can only touch files it created itself; it cannot
read anything else in your Drive."

**Pick `private-links`** when users habitually paste private Google Docs/Slides links into
the chat and expect the bot to read them.

Set it with an environment variable on the server:

```bash
# in ~/.hermes/.env  (or export it before running authorize)
DOC_CONVERT_GOOGLE_SCOPES=minimal        # or: private-links
```

Changing the scope set **after** authorizing requires authorizing again — the grant
recorded in the token is what counts, not the variable.

---

## 3. Create a Google Cloud project

1. Open <https://console.cloud.google.com/> signed in as **the Google account whose Drive
   should hold the files**. Getting this wrong puts every future file in the wrong place.
2. Top left, open the project picker → **New Project**.
3. Give it a recognisable name (e.g. `hermes-doc-convert`) → **Create**.
4. Wait a moment, then select that project. Check the name in the top bar — working in the
   wrong project is the most common cause of trouble in the steps below.

---

## 4. Enable the APIs

Go to **APIs & Services → Library** and enable:

| API | Required? | Used for |
| --- | --- | --- |
| **Google Drive API** | **Yes** | Upload the file, convert it to Google Slides/Docs, export it back to PDF/pptx/docx |
| **Google Slides API** | Recommended | Read the deck back after import to check layout and text contrast |
| Google Docs API | No | Never called — content arrives by import, not by batchUpdate |

Without the Slides API, conversion still works; only the automatic check reports
`google_check.status: "unchecked"` — which means **not verified**, not "passed".

---

## 5. Configure the consent screen — and PUBLISH

Go to **APIs & Services → OAuth consent screen**.

1. User type: **External** → **Create**.
   (*Internal* is only available when the customer has Google Workspace and only people
   inside that organisation will use the bot. A normal Gmail account is always External.)
2. Fill in the minimum: **App name** (e.g. "Hermes Document Assistant"), **User support
   email**, **Developer contact email**. No logo, no domain verification.
3. Save through the remaining pages until you return to the summary screen.
4. Look at **Publishing status**. If it reads **Testing**, click **PUBLISH APP** and
   confirm. It must end up as **In production**.

> ### Why item 4 is mandatory
>
> While the app sits in **Testing**, Google expires refresh tokens after **exactly seven
> days**. The bot runs perfectly for a week, then dies with `invalid_grant` in the log,
> and nobody can explain it because nothing changed. Publishing removes that rule.
>
> Publishing does **not** list the app publicly. It is only a release state. An unverified
> app is still capped at 100 users and, with the `private-links` scope set, still shows the
> unverified-app warning at sign-in.

---

## 6. Create the OAuth client and download the JSON

Go to **APIs & Services → Credentials**.

1. **Create credentials → OAuth client ID**.
2. Application type: **Desktop app** ← this exact type. *Web application* demands a
   registered redirect URI and breaks the terminal sign-in flow.
3. Name it anything → **Create**.
4. Click **Download JSON** and keep the file safe — it is the app's secret.

> Google only offers the JSON download for a **newly created** client. If it is ever lost,
> do not hunt for a way to re-download it: create a new Desktop client (a minute's work)
> and authorize again.

---

## 7. Install it on the server and authorize once

The two routes split here. **Route A** happens in chat, **Route B** in a terminal; the
result is identical (`client_secret.json` + `token.json`, mode 600, in one directory).

### Route A — in chat, no SSH tunnel

The user says *"Connect Google for me"*, the bot narrates steps 3–6 above, and then:

1. The user forwards the **downloaded JSON file** into the chat, or pastes the **Client ID
   and Client secret**. The bot checks it really is a Desktop client and stores it in the
   credentials directory on the server.
2. The bot sends a **consent link**. The user opens it, picks the account, presses
   **Allow**.
3. The browser lands on **"This site can't be reached"** — the redirect target is
   `http://localhost:8765` and nothing is listening on the user's own machine. **That is
   the correct outcome**: the authorization code is sitting in the address bar.
4. The user copies **the entire address** and pastes it into the chat. The bot exchanges
   it for a refresh token, writes `token.json`, and reports **which Google account** got
   connected so the user can confirm it is the right one.

Step 3 is what replaces the SSH tunnel: a Desktop OAuth client is allowed to redirect to
loopback, and **nothing has to be listening there** — the address itself carries the code.

> **A trade worth stating plainly:** in step 1 the `client_secret` (or the whole JSON file)
> travels through Telegram and stays in the user's chat history. In exchange they do it
> themselves and never hand their secret to the installer. Delete that message once
> connected; for a stricter posture, create a new client and delete the old one in the
> console. Anyone who will not accept that risk should use Route B.

The bot uses PKCE and checks the `state` parameter, so a stale or foreign link is refused
rather than silently used. Consent links are valid for **one hour**; after that, ask the
bot for a fresh one.

Chat-specific failures are in the table in [Section 10](#10-troubleshooting).

### Route B — terminal (installer with SSH access)

Copy the JSON to the server, named exactly `client_secret.json`:

```bash
# from your machine
scp ~/Downloads/client_secret_*.json <user>@<vps>:~/hermes-google-creds/client_secret.json
```

On the server, create the directory and tighten permissions:

```bash
mkdir -p ~/hermes-google-creds && chmod 700 ~/hermes-google-creds
chmod 600 ~/hermes-google-creds/client_secret.json
```

Point the skill at it — add to `~/.hermes/.env`:

```bash
DOC_CONVERT_GCREDS_DIR=/home/<user>/hermes-google-creds
DOC_CONVERT_GOOGLE_SCOPES=minimal          # or private-links
```

> You may drop `DOC_CONVERT_GCREDS_DIR` and use the default path
> `skills/doc-convert/state/google-creds/` instead. Keeping credentials **outside** the
> repository is safer: repositories get copied, zipped and occasionally committed by
> accident. If the repository lives on a Windows drive mounted into WSL (`/mnt/c/...`),
> outside is mandatory — `chmod 600` has no effect there.

Authorize — **once for the lifetime of the install**:

```bash
cd <repo directory>
python3 skills/doc-convert/scripts/authorize_google.py --port 8765
```

It prints the scope set being requested and a URL. A VPS has no browser, so open an SSH
tunnel from your machine to let your browser reach port 8765 on the server:

```bash
# on your machine; keep this session open while you click through consent
ssh -L 8765:localhost:8765 <user>@<vps>
```

Then open the printed URL:

1. Choose **the same Google account** used in Step 3.
2. If *"Google hasn't verified this app"* appears → **Advanced** → *Go to … (unsafe)*.
   Normal for an unverified app; the `minimal` scope set never shows this screen.
3. Review the permissions and click **Continue / Allow**.
4. The browser shows "Done! You can close this tab…" and the terminal prints the path of
   the `token.json` it saved (mode 600).

---

## 8. Verify

In chat (fastest, and the user can do it): *"Check my setup"*. The bot runs
`check_setup.py`, and for Google it runs one real conversion and sends back the link —
evidence rather than a claim.

In a terminal:

```bash
python3 skills/doc-convert/scripts/preflight.py --compact | python3 -m json.tool
```

The `google` block should read:

```json
"google": {
  "libs_installed": true,
  "creds_dir": "/home/<user>/hermes-google-creds",
  "client_secret": true,
  "authorized_token": true,
  "scope_set_requested": "minimal",
  "granted_scopes": ["https://www.googleapis.com/auth/drive.file"],
  "can_read_private_links": false
}
```

`granted_scopes` is read from the **token itself**, not from configuration — it is what
the bot can actually do. With `minimal`, `can_read_private_links: false` is correct, not a
fault.

Run one real conversion:

```bash
python3 skills/doc-convert/scripts/convert.py \
  --input docs/user-guide.en.md --to gslides --no-auto-images --outdir /tmp/oauth-check
```

The JSON should contain:

- `"success": true`
- `"render_engine": "google"` — Google drew the file, not the local libraries
- `"google_url"` — opens in a browser; the file is private in the customer's Drive
- `"google_check": {"status": "pass"}` — the imported deck was read back and checked
- `"output"` — path of the PDF Google exported

Open `google_url` and look through it. This is also the moment for the customer to confirm
the file landed in the Drive account they expected.

---

## 8b. Testing against real Google (once, ~10 minutes)

The offline rehearsal covers the mechanics of the chat flow:

```bash
python3 skills/guided-setup/scripts/selftest.py
```

It runs the same commands the bot runs, against a throwaway `HERMES_HOME` and a **fake
Google** on localhost, so it proves: the code is extracted correctly from the pasted
address, the right parameters go out (PKCE verifier, matching redirect_uri), the token
file we write loads with the library doc-convert uses, and all three failure modes
(expired code, stale link, no refresh token) come back as sentences someone can act on.
What it cannot prove is Google's real consent screen.

That part is one manual pass with a real Google account — ideally the customer's, during
handover. Play the user: say *"Connect Google for me"* and watch these six points:

| # | What to watch | Passes when |
| --- | --- | --- |
| 1 | The bot asks about private Google links | It asks, and explains both options briefly |
| 2 | Console instructions | Short messages, one screen at a time; **PUBLISH APP** and **Desktop app** both emphasised |
| 3 | After the client is sent | It confirms storage and does **not** echo the client secret back |
| 4 | The page after pressing Allow | The bot warned **in advance** that the error page is expected (this is where users panic) |
| 5 | After the address is pasted | It names the **connected account's email** and asks for confirmation |
| 6 | `google_setup.py test` | `success: true`, `render_engine: google`, and `google_url` opens a private file in the customer's Drive |

Then try the two failures customers actually hit:

- **Slow paste.** Take the consent link, wait 10+ minutes before pressing Allow, then
  paste. The bot must say the link expired and offer a new one — not stall or emit a
  technical error.
- **Wrong paste.** Send *"I pressed allow but it showed an error"* instead of the address.
  The bot must ask for exactly the right thing: the **whole address line** of the error
  page.

Afterwards, delete the test file from Drive and the message containing the client secret.

---

## 9. Security and privacy — answers for the customer

- **What can the bot read in my Drive?** With `minimal`: only files it created itself. It
  cannot list, open or delete anything else. With `private-links`: files you can read, and
  only when you paste a link yourself.
- **Who can see the files it creates?** Only you. They are private in your own Drive and
  the bot never changes sharing. Share them yourself if you want to.
- **Who holds my Google password?** Nobody. The bot never sees it; it holds a refresh
  token issued by Google, which you can revoke at any time.
- **How do I revoke?** <https://myaccount.google.com/permissions> → select the app →
  **Remove access**. The bot fails on its next run until it is authorized again.
- **Where do the secrets live on the server?** `client_secret.json` and `token.json`, mode
  600, inside `DOC_CONVERT_GCREDS_DIR` (mode 700). `.gitignore` already excludes
  `**/google-creds/`, `token.json` and `client_secret.json` — but keep them out of the
  repository anyway.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Works for days, then fails with `invalid_grant` | App still in **Testing** → 7-day token expiry | Publish the app (Step 5), then re-run `authorize_google.py` |
| `Chưa authorize Google. Chạy 1 lần: …` | No `token.json`, or wrong `DOC_CONVERT_GCREDS_DIR` | Check with preflight, then authorize again |
| `THIẾU …/client_secret.json` | JSON not copied over, or misnamed | Rename it to exactly `client_secret.json` |
| Browser reports `redirect_uri_mismatch` | Client created as **Web application** | Recreate it as a **Desktop app** client |
| Browser hangs, then cannot reach `127.0.0.1:8765` | No SSH tunnel, or the port is taken | Open the tunnel; or use `--port 8766` and adjust the tunnel |
| `access_denied` | Cancelled the dialog, or app in Testing and the account is not a Test user | Publish the app, or add the account to Test users |
| Bot replies that it can only touch files it created and cannot read private links | Running the `minimal` scope set | Upload the file directly, or re-authorize with `private-links` |
| `google_check.status: "unchecked"` | **Google Slides API** not enabled | Enable it and re-run; the deck itself is fine |
| A link but no PDF, plus a `google_export_failed` warning | Drive refuses exports over **10 MB** | Normal for photo-heavy decks — the link is the deliverable |
| `warnings: ["google_unauthorized:rendered_locally"]` | No token; the file was rendered locally | Finish Step 7; the current file may look wrong on a Mac |

### Chat route only (Route A)

| The bot reports | Cause | Fix |
| --- | --- | --- |
| `no_code_in_url` | The user pasted a description or screenshot instead of the address | Ask for the **whole address line** of the error page after pressing Allow |
| `authorization_expired` | The consent link is over an hour old | Ask the bot for a new link and finish within a few minutes |
| `token_exchange_failed:invalid_grant` | The code was already used, or is minutes old | Get a fresh link; each one works once |
| `state_mismatch` | An older attempt's link was pasted | Use only the most recent link the bot sent |
| `no_refresh_token` | This account authorized before, so Google withheld a new refresh token | Remove the app at <https://myaccount.google.com/permissions> and authorize again |
| `wrong_client_type:web` | Client created as a Web application | Recreate it as a **Desktop app** (Step 6) |
| `consent_error:access_denied` | Cancelled, or app in Testing and the account is not a test user | Publish the app (Step 5), then authorize again |
| `no_json_found` / `invalid_json` | Truncated paste, or a screenshot | Forward the JSON file itself, or paste **Client ID + Client secret** |

---

## 11. Maintenance

- **Nothing recurring** once the app is published: refresh tokens renew themselves.
- **Switching Google account**: the user says *"Reconnect Google with another account"* —
  the old token is overwritten. Terminal route: delete `token.json` and re-run
  `authorize_google.py`. Old files stay in the old account's Drive.
- **Leaked client secret**: delete the client in Credentials, create a new Desktop client,
  then reconnect (chat: send the bot the new client; terminal: copy the new JSON up and
  authorize again).
- **Changing scope set**: the user says *"Reconnect Google with private link access"*.
  Terminal route: edit `DOC_CONVERT_GOOGLE_SCOPES`, delete `token.json`, authorize again.
- **Clearing test files**: files the bot created during testing sit in the customer's
  Drive like any other file — delete them by hand, or leave them; they are private.

---

Vietnamese version: [google-oauth-setup.vi.md](google-oauth-setup.vi.md) ·
Operations: [operator-runbook.en.md](operator-runbook.en.md)
