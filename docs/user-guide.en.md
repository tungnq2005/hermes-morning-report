# User Guide — AI Assistant on Telegram

Your assistant works entirely through **Telegram chat** with a bot. You never touch the server, code, or any settings — just message it in plain language.

Bot: **@your_bot** (open Telegram, search this name, press Start).

The assistant has two main capabilities:

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

---

## 2. Document Conversion & Narration

Send the bot a **file** (drag-and-drop into chat) or a **public Google link**, with your request.

### Supported formats
- **Input**: Word (.docx), PowerPoint (.pptx), text-based PDF, Text/Markdown, Google Docs/Slides/Drive links (set to "Anyone with the link").
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
- Anything else? Just message the bot in natural language — it understands plain requests.
