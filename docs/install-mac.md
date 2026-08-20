# Installing the morning report bot on a Mac

For a Mac that stays **switched on and logged in** — a Mac Studio or Mac mini used as
an always-on machine. For a rented Ubuntu server, use `setup/setup_all_hermes.sh` instead.

One command installs everything: the morning report **and** document conversion
(Word / PowerPoint / PDF).

---

## Before you start: collect 4 keys

Do this part first, in a browser, and paste the keys into a note. The installer asks
for them one at a time and checks each one immediately, so a wrong key is caught
straight away rather than at 8am tomorrow.

| # | Service | What it does | Where | Cost at 1-2 topics |
|---|---------|--------------|-------|--------------------|
| 1 | **Telegram bot** | The bot you chat with | Telegram → search **@BotFather** → `/newbot` → follow the questions → copy the long token | Free |
| 2 | **DeepSeek** | Writes the report | [platform.deepseek.com](https://platform.deepseek.com) → API keys → create | **Needs prepaid balance** — a few dollars covers about a year |
| 3 | **Exa** | Finds the news | [exa.ai](https://exa.ai) → sign up → API key | Free (20,000 searches/month; you use ~60) |
| 4 | **Firecrawl** | Reads the pages it finds | [firecrawl.dev](https://firecrawl.dev) → sign up → API key | Free tier ≈ 1,000 page reads/month; you use ~400-600 |
| 5 | Brave Search | Optional backup search | [brave.com/search/api](https://brave.com/search/api) | Optional — you can skip it |

**Check the Firecrawl dashboard when you sign up.** Firecrawl has advertised both
"1,000 credits per month" and "1,000 credits total" at different times. If your
account says the allowance is one-off, tell whoever is doing the handover — with
2 topics it lasts about two months and then reports stop until the plan is upgraded.

**Two topics maximum** is the recommended setup. Each report uses 1 search and
5-10 page reads. Three or more topics can push Firecrawl past its free allowance.

You also need the **administrator password of this Mac** (the one you use to
install software) — the installer asks for it once, to stop the Mac sleeping.

---

## Install

1. Open **Terminal**: press `Cmd` + `Space`, type `Terminal`, press Enter.
2. Copy this line, paste it into the Terminal window, press Enter:

   ```
   curl -fsSL https://<host>/install-mac.sh | bash
   ```

   (Ask support for the exact line — the `<host>` part is filled in for you.)
3. Answer the questions. Nothing appears on screen while you paste a key — that is
   deliberate, it keeps the keys out of the screen and out of the log.

Roughly 40-60 minutes in total, most of it waiting for downloads. The Terminal
window must stay open until it says **Installation finished**.

### What the installer asks you

| Step | What you do |
|------|-------------|
| 3 | Paste the 4 keys (Brave optional). Each is checked on the spot. |
| 4 | Hermes' own setup screens: choose **DeepSeek**, paste the DeepSeek key → choose **Telegram**, paste the bot token → your Telegram user id → the chat to send to |
| 7 | Type your Mac password when it asks to turn off sleep — **say yes**, see `limits-mac.md` |
| 8 | Your topics (1-2), the delivery time (e.g. `08:00`), and the report language |
| 9 | Watch Telegram. A real report is sent within ~8 minutes as a test, then the time is set back to your real one |
| 10 | Document conversion installs itself. It may ask to install Homebrew (a standard Mac software installer) — say yes |

### macOS dialogs you may see

- **"Terminal would like to access files"** → Allow.
- **A password prompt in Terminal** (`Password:`) → your Mac login password. Nothing
  appears as you type; that is normal.
- **"Install the command line developer tools?"** → click Install and wait, then run
  the install command again.
- Homebrew asking to install Xcode command line tools (about 2 GB) during step 10.

---

## When it finishes

- The bot sends the report every day at the time you chose.
- Ask for one at any time: message the bot **"send report"**.
- Something looks wrong: run `hermes-check` in Terminal and send the output to support.
- Change topics or time later: message the bot, e.g. *"change the morning report time
  to 07:30"*, or *"add a topic: gold price"*.

Read `limits-mac.md` next — it is one page and it explains the two rules that keep
the bot working (stay on, stay logged in).

---

## If the install stops part-way

Run the same command again. It skips everything already done and does not ask again
for keys it already saved. If it stops twice, send `~/hermes-install.log` to support —
it contains no keys, they are masked.

---

## Optional: Google Docs and Slides

Document conversion works out of the box with files sent to the bot in Telegram.
Reading your private Google Drive or writing Google Slides drafts needs a Google
Cloud project and a browser sign-in, so it is a separate step done with support:

```bash
python3 ~/.hermes/skills/doc-convert/scripts/authorize_google.py
```
