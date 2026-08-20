# Key guides — English (source text for what you send the user)

For the **assistant**, not to be forwarded verbatim. Each section is already broken into
short steps you can send one message at a time. Rules: **one service at a time**, links
on their own line, then stop and wait for the user to paste.

If the user describes a screen that does not match what is written here (providers
redesign often), do not guess — ask what they see and follow that.

---

## Exa — news search (required for Morning Report)

**Say first:** this is what finds the last 24 hours of news for the briefing. Free tier,
no card needed to start.

Steps to send:

1. Open this link: https://dashboard.exa.ai/api-keys
2. Sign in with Google (or email); first time, sign up.
3. Press **Create API Key**, name it anything, e.g. `hermes`.
4. Press the copy icon.
5. Paste it here.

**What the key looks like:** a long dashed string like
`a1b2c3d4-e5f6-7890-abcd-ef1234567890`. Not a web address, not an email.

**Common snag:** the key is shown in full only once. If they closed the dialog without
copying, have them create a new key — faster than hunting for the old one.

Save with: `save_key.py --name exa --value "<what the user pasted>"`

---

## Firecrawl — article reader (recommended)

**Say first:** it lets the bot read the full article text instead of just headlines.
Without it the briefing still works, just thinner on some news sites. Free tier
available.

Steps to send:

1. Open this link: https://www.firecrawl.dev/app/api-keys
2. Sign in or sign up (Google sign-in is fastest).
3. Under **API Keys**, copy the existing key or create a new one and copy it.
4. Paste it here.

**What the key looks like:** starts with `fc-`, e.g. `fc-1a2b3c4d...`.

Save with: `save_key.py --name firecrawl --value "<what the user pasted>"`

---

## Brave Search — search fallback (optional)

**Say first:** used only when Exa fails or runs out of credits, so the morning briefing
is never empty. Safe to skip and add later.

Steps to send:

1. Open this link: https://api-dashboard.search.brave.com/app/keys
2. Sign up or sign in.
3. Subscribe to the **Free** plan. Brave may ask for a card to verify even on the free
   plan — if the user would rather not, **skip this service**; everything else still
   works.
4. Go to **API Keys** → create a key → copy it.
5. Paste it here.

**What the key looks like:** usually starts with `BSA`, e.g. `BSAxxxxxxxxxxxxxxxx`.

Save with: `save_key.py --name brave --value "<what the user pasted>"`

---

## Google — Slides/Docs output (optional, for Document Conversion)

The long one: about 10 minutes of browser clicks plus **two pastes** into the chat. The
reasoning behind each screen is in `docs/google-oauth-setup.en.md`.

**Say first:** the bot builds slides and documents **inside the user's own Google
Drive**, so they look identical on Mac, Windows and iPad. Files stay private in their
Drive; the bot sees nothing else and never sees their Google password.

**Ask once, first:** does the user want the bot to open *private* Google Docs/Slides
links they paste into chat?
- **No** (default) → `minimal`: the bot only touches files it created, and there is **no
  warning screen** during consent.
- **Yes** → `private-links`: the bot can read files the user can see, but consent goes
  through a *"Google hasn't verified this app"* screen.

### G1. Create the Google Cloud project

1. Open this link with **the Google account whose Drive should hold the files**:
   https://console.cloud.google.com/
2. Top bar, project selector → **New Project**.
3. Name it anything, e.g. `document-assistant` → **Create**.
4. Wait a few seconds, then select that project in the top bar.

### G2. Turn on Google Drive access

1. Go to **APIs & Services → Library**.
2. Search `Google Drive API` → open → **Enable**.
3. Search `Google Slides API` → **Enable**. (Optional: without it the bot cannot
   double-check a deck after creating it.)

### G3. Register the app — and **PUBLISH** it

1. Go to **APIs & Services → OAuth consent screen** (newer console: **Google Auth
   Platform**).
2. Choose **External** → **Create**.
3. Fill in app name, support email, contact email. No logo, nothing else. Save through
   the steps.
4. **The step that matters:** find **Publishing status** (newer console: **Audience**) →
   **PUBLISH APP** → confirm. It must read **In production**.

> Tell the user why step 4 is not optional: left in **Testing**, Google expires the
> connection after exactly **7 days** and the bot silently stops working a week later.
> Publishing does **not** expose the app to strangers — it is only a release state.

### G4. Create the OAuth client — **Desktop app**

1. Go to **APIs & Services → Credentials**.
2. **Create credentials → OAuth client ID**.
3. Application type: **Desktop app** ← this one. *Web application* breaks the last step.
4. Any name → **Create**.
5. Press **Download JSON**, or leave the dialog showing **Client ID** and **Client
   secret** on screen.
6. Send it here **either way**:
   - forward the downloaded JSON file into this chat, **or**
   - copy the **Client ID** and **Client secret** and paste them here.

Save with: `google_setup.py client --file <path>` · `--json "<pasted text>"` ·
or `--client-id ... --client-secret ...` (add `--scopes private-links` if the user chose
private links).

### G5. One press of Allow

Run `google_setup.py start`, send `auth_url` **on its own line**, then say, in this
order:

1. Open the link and pick **the same Google account** as before.
2. (`private-links` only) If *"Google hasn't verified this app"* appears → **Advanced** →
   **Go to … (unsafe)**. Normal for a private app.
3. Press **Continue / Allow**.
4. The browser will land on an **error page** (*"This site can't be reached"*). **That
   means it worked** — say this before they see it, or they will report it as a bug.
5. Copy the **entire address** from that error page's address bar and paste it here.

Finish with: `google_setup.py finish --redirect-url "<what the user pasted>"`

### G6. Prove it

Run `google_setup.py test`, send `google_url` as a clickable link, and tell the user the
file is private in their Drive and safe to delete.

---

## When the user pastes the wrong thing

`save_key.py` detects these and returns them in `problems`. Relay them as plain
sentences; never read an error code out to the user:

| `problems` | What to say |
| --- | --- |
| `looks_like_url` | "That's the web address of the page. The key is the string shown **on** that page." |
| `looks_like_email` | "That's the sign-in email, not the key." |
| `contains_spaces` | "Looks like some surrounding text came along — just the key line, please." |
| `placeholder` | "That's the example text on screen, not a real key yet." |
| `too_short` | "Part of the key is missing — could you copy the whole line again?" |
| `verify.state: rejected` | "The provider says this key doesn't work. Could you create a new one and send it?" |
