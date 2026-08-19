# Connecting Google Workspace for Document Conversion

This guide is for whoever **installs** the bot — you, or the customer's technician. End
users never read it; they click "Allow" once, in Step 7.

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

```bash
python3 skills/doc-convert/scripts/preflight.py --compact | python3 -m json.tool
```

The `google` block should read:

```json
"google": {
  "libs_installed": true,
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

---

## 11. Maintenance

- **Nothing recurring** once the app is published: refresh tokens renew themselves.
- **Switching Google account**: delete `token.json`, re-run `authorize_google.py`, sign in
  as the new account. Old files stay in the old account's Drive.
- **Leaked client secret**: delete the client in Credentials, create a new Desktop client,
  copy the new JSON to the server, authorize again.
- **Changing scope set**: edit `DOC_CONVERT_GOOGLE_SCOPES`, delete `token.json`,
  authorize again.
- **Clearing test files**: files the bot created during testing sit in the customer's
  Drive like any other file — delete them by hand, or leave them; they are private.

---

Vietnamese version: [google-oauth-setup.vi.md](google-oauth-setup.vi.md) ·
Operations: [operator-runbook.en.md](operator-runbook.en.md)
