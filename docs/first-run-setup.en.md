# First-time setup — all of it in chat

For **you, the person using the bot**. No server knowledge, no software to install, nobody
else needed. A phone or computer with Telegram and a browser is enough.

Total time: **10 minutes** for the morning briefing, **20 minutes** if you also want
document conversion.

---

## Start here

Open Telegram, find **@your_bot**, press **Start**, and send:

> **Set up the assistant for me**

The bot checks what is missing and walks you through it **one step at a time**. Follow
along; if you get stuck, just say so — *"I don't see that button"* — and it will guide you
again.

You can stop halfway. Whatever is connected stays connected; say *"continue the setup"*
whenever you have time and it picks up where you left off.

---

## What the bot will ask you for

### 1. Search keys (for the morning briefing)

| Service | What it does | Required? |
| --- | --- | --- |
| **Exa** | finds the last 24 hours of news on your topics | **Yes** — no briefing without it |
| **Firecrawl** | reads the full article, not just the headline | Recommended |
| **Brave Search** | backup search when Exa fails or runs out | Optional |

All three have **free tiers**. For each one the bot sends you a link, tells you exactly
where to click to create an "API key", and you **copy and paste it into the chat**. The
bot checks it with the provider right away and tells you whether it works.

> An "API key" is just a long line of text — a password for apps. You don't need to
> understand it, only to copy the right line.

### 2. Topics and delivery time

The bot asks in plain language: which topics, what time, which language, concise or deep
analysis, audio or not. Answer naturally. It summarises everything back and only saves
once you confirm.

### 3. Connecting Google (only for document conversion)

So that the files it makes look identical on Mac, Windows and iPad, the bot builds slides
and documents **inside your own Google Drive**. That needs your permission, once.

Two things to do:

1. Create an "app" in Google's admin site (the bot walks you through every button, about 8
   minutes, free), then send it the details it asks for.
2. Tap the link the bot sends → pick your Google account → press **Allow**.

**Read this part carefully:** after you press Allow, your browser will land on an **error
page** (*"This site can't be reached"*). **That is what success looks like.** Just copy
**the entire address from the address bar** of that error page and paste it into the chat.
The bot handles the rest.

Then it runs one real test file and sends you the link so you can see it worked.

Connecting Google also unlocks one more thing: **your morning reports become documents**
on request — *"Send today's report as a Google Doc"*, *"Make slides from yesterday's
report"* — with no file to send back.

---

## Worth knowing

- **The bot never sees your Google password.** You sign in on Google's own page; the bot
  only receives permission to create files.
- **Files it creates are private in your Drive.** Nobody else can open them unless you
  share them yourself.
- **It can only touch files it created** — unless you choose to let it read private links,
  which it asks about first and explains.
- **You can revoke access any time** at <https://myaccount.google.com/permissions> →
  select the app → *Remove access*.
- **Never send passwords or card numbers to the bot.** No step needs them. If something
  asks you to, it is not this process.

---

## If something goes wrong

| What you see | Say to the bot |
| --- | --- |
| Not sure what's missing | *"Check my setup"* |
| A key was rejected | *"I made a new key, replace it"* |
| No morning briefing arrived | *"Run the morning report now"* |
| It says Google isn't connected | *"Connect Google for me"* |
| It can't open a private Google link you pasted | *"Reconnect Google with private link access"* |
| You want a different Google account | *"Reconnect Google with another account"* |

No answer after 2 minutes? Tell the operator — at that point it is a server matter, not
yours.

---

Vietnamese: [first-run-setup.vi.md](first-run-setup.vi.md) ·
Day-to-day use: [user-guide.en.md](user-guide.en.md) ·
Quick reference: [chat-commands.md](chat-commands.md)
