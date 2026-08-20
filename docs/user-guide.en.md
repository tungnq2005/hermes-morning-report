# User Guide — AI Assistant on Telegram

Your assistant works entirely through **Telegram chat** with a bot. You never touch the server, code, or any settings — just message it in plain language.

Bot: **@your_bot** (open Telegram, search this name, press Start).

The assistant has two main capabilities:

---

## 0. First time: say "Set up the assistant for me"

Before it can work, the assistant needs a few "keys" to search the news with and — if you
want document conversion — permission to create files in your own Google Drive. **All of
it happens in this chat.** No server, nobody to do it for you.

> **Set up the assistant for me**

The bot checks what is missing, sends you a link, shows you where to click to get each
key, and you **paste the key into the chat**. It verifies each one with the provider
before saving. About 10 minutes for the morning report, 20 if you also want document
conversion. You can stop halfway and say *"continue the setup"* later.

Step-by-step, including the Google part: [first-run-setup.en.md](first-run-setup.en.md).

Already using it and something says a key is missing or Google isn't connected? Say
*"Check my setup"*.

---

## 1. Morning Report

Every morning the bot automatically sends you a briefing on the topics you care about — a **text report** plus a **3–5 minute audio file** to listen to on the go.

### First-time setup
Send:
> Set up Morning Report for me

The bot asks, one by one: topics to follow, delivery time, timezone, style (concise / deep analysis / opportunities & risks), language, and whether to include audio. Answer naturally. It then **summarizes the configuration and waits for your confirmation** — reply "OK" / "confirm" to save.

### Daily use
- **Preview now** (don't wait for tomorrow): *"Run the morning report now"*
- **Change topics**: *"Change topics to stocks and gold prices"*
- **Add / remove a topic**: *"Add technology news"* / *"Remove weather"*
- **Change delivery time**: *"Send the report at 6:30 AM"*
- **Change style / language**: *"Switch to deep analysis style"*
- **Pause**: *"Pause the morning report"*
- **Resume**: *"Resume the morning report"*
- **View current settings**: *"What's my morning report configuration?"*

### Turn a report into a document
The bot still has every report it sent you, so **you never need to send anything back**:
- *"Send today's report as a Google Doc"* → a Google Docs link plus a PDF copy
- *"Make slides from yesterday's crypto report"* → a Google Slides link plus a PDF copy
- *"Send that report as a PDF"*
- *"Which reports can you export?"* → the bot lists the stored reports so you can pick one

The exported copy comes **illustrated** with openly licensed photos, credited at the end:
one per section in a document, and a cover photo on a deck — slides full of figures keep
their stat cards instead. Say *"export it without pictures"* if you'd rather have none.

Ask twice for the same report and you get **the same file back**, not a duplicate in your
Drive; say *"make a new one"* if you really want a second copy.

To skip asking every day: *"Always save the gold report to Google Docs"* — from then on
every report for that topic arrives with its Google Docs link attached. Turn it off with
*"Stop saving the gold report to Google Docs"*. (Needs Google connected; it adds one file
to your Drive per report.)

---

## 2. Document Conversion & Narration

Send the bot a **file** (drag-and-drop into chat) or a **public Google link**, with your request.

### Supported formats
- **Input**: Word (.docx), PowerPoint (.pptx), text-based PDF, Text/Markdown, Google Docs/Slides/Drive links (set to "Anyone with the link"), **or a Morning Report you already received** (no file needed — see section 1).
- **Output**: **Google Slides / Google Docs** (the default), plus PowerPoint, Word, PDF, Markdown, or MP3 audio.

### How to use
- **Word → slides**: send a .docx with *"Convert this to PowerPoint"* → you get a **Google Slides link** plus a PDF copy
- **→ PDF**: *"Export this as PDF"*
- **PowerPoint → document**: send a .pptx with *"Turn these slides into a Word document"*
- **From a Google link**: paste the link with *"Convert this document to slides"* (reads **private** files in the connected Google account too)
- **Still want an Office file?** Ask for it: *"Send me the .pptx file too"*
- **Narrate as audio**: send a file with *"Read this document as audio"*

The bot returns a Google link and, alongside it, a PDF attachment in the chat. Turnaround is usually **5–10 minutes** depending on length.

### Why Google Slides / Google Docs?
A PowerPoint file generated on the server does not always draw the same way in PowerPoint for Mac — fonts, spacing and layout shift. Google renders the deck once, so it looks identical on macOS, Windows, iPad and in the browser, and any .pptx/.docx/.pdf you ask for is exported from that same Google file.

### Notes
- Files created for you live in **your own Google Drive and stay private** — nobody else can open the link. Share it yourself if you want to.
- Private Google files **are now readable** through the connected account. Files others shared with that account work too, if it has access.
- Scanned image-only PDFs (no text) are not supported.
- Video editing/generation is **out of scope** (a separate future feature).

---

## Troubleshooting
- Bot not replying? Wait 1–2 minutes (it may be processing). If still silent, contact your operator.
- No morning report? Check you haven't "paused" it; send *"Run the morning report now"* to test.
- It says a key is missing, a key was rejected, or Google isn't connected? Say *"Check my setup"* — the bot diagnoses it and walks you through reconnecting, right here in chat.
- Got a file back with a note about "rendered locally"? That means Google isn't connected; say *"Connect Google for me"*.
- Anything else? Just message the bot in natural language — it understands plain requests.
