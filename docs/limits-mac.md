# What this setup can and cannot do (Mac)

## Two rules

> **1. This Mac must stay switched on.**
> **2. Someone must be logged in.**

The report is not produced somewhere on the internet — it is produced by a program
running on this Mac. Sleeping, shut down, or sitting at the login screen means no
report, and no error message either.

After a restart (power cut, macOS update), **log in again**. The bot starts by itself
about a minute after you log in. Nothing else to do.

---

## Full list of limitations

| # | Limitation | How bad | What we did about it |
|---|------------|---------|----------------------|
| 1 | If the Mac sleeps, the bot pauses and no report is sent | High | The installer turns sleep off (`pmset -a sleep 0`). The screen can still turn off — that is fine. If you ever see reports stop, check that sleep is still off. |
| 2 | The background service can fail to restart after a Hermes update | High | The service is set to restart automatically, and the watchdog restarts it if it dies |
| 3 | The bot could die without anyone noticing | High | A watchdog **outside** the bot checks every 15 minutes. If the bot is dead or stuck it restarts it; if that fails it messages you on Telegram directly |
| 4 | After a restart, someone must log in before the bot runs | Medium | **Accepted — this is by design.** Log in and it comes back |
| 5 | Logging in late means the report is late | Medium | Within 2 hours of the delivery time it catches up quietly. Later than that, it still sends **one** report shortly after you log in — you do not lose the day, it just arrives late. You can also ask the bot "send report" |
| 6 | You register the API accounts yourself, and DeepSeek needs prepaid balance | Medium | The installer gives you the signup links and checks each key on the spot. Cost at 1-2 topics: a few dollars per year |
| 7 | Creating the bot in @BotFather means copying a long token | Medium | The installer checks the token and prints your bot's name so you can confirm it is the right one |
| 8 | Reading logs when something fails is not something you should have to do | Medium | Everything is logged to `~/hermes-install.log`, and `hermes-check` prints one block you can copy and send to support |
| 9 | LibreOffice is not visible to the converter by default on macOS | Medium | The add-on links it into place during install |
| 10 | Nobody can log in remotely to fix things | Low | **Accepted — you asked for no remote access.** Everything is diagnosed from the `hermes-check` output you send |
| 11 | Full disk or hardware failure | Low | The 15-minute check reports low disk space |

---

## Not covered (you decided against these)

- **Power cuts / UPS.** If the power goes out, the Mac goes off. When it comes back,
  someone logs in and the bot resumes. No battery backup is installed.
- **Automatic login after a restart.** The Mac stops at the login screen until a
  person logs in. (Automatic login would mean turning off disk encryption.)
- **Running without anyone logged in** (a system-level service).
- **Remote access** (Tailscale, SSH, screen sharing). All support happens by phone
  plus the `hermes-check` output.
- Blocking macOS automatic updates. An update reboots the Mac — log in afterwards.

---

## Reasonable expectations

- One report per topic per day, at the time you chose, in Telegram — text plus a
  3-5 minute audio version.
- Between 1 and 2 topics. More is possible but may cost money (Firecrawl allowance).
- Document conversion: send a `.docx`, `.pptx`, `.pdf` or Markdown file to the bot and
  ask for the format you want.
- If you go away for a week and nobody touches the Mac: reports keep arriving, as long
  as the power and the internet stay on.
