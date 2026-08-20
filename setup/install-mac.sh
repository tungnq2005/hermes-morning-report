#!/usr/bin/env bash
# One-command installer for the Hermes morning-report bot on an always-on Mac
# (Mac Studio / Mac mini that stays powered on and logged in).
#
#   curl -fsSL https://<host>/install-mac.sh | bash
#
# Installs BOTH skills: morning-report (D1) directly, then doc-convert (D2) by
# chaining install-doc-addon.sh at step 10 as a trapped subprocess — a failure in
# the document-conversion dependencies (Homebrew, Xcode CLT, LibreOffice) must
# never take down the morning report.
#
# For the Ubuntu VPS path use setup_all_hermes.sh instead — that one is not
# portable to macOS (apt, systemd, getent).
set -euo pipefail

MR_REPO_REF="${MR_REPO_REF:-main}"
MR_REPO_TARBALL="${MR_REPO_TARBALL:-https://codeload.github.com/tungnq2005/openclaw-morning_report/tar.gz/refs/heads/${MR_REPO_REF}}"
MR_SOURCE_DIR="${MR_SOURCE_DIR:-}"          # set automatically; override for testing
INSTALL_LOG="$HOME/hermes-install.log"
HERMES_ENV_FILE="$HOME/.hermes/.env"
HERMES_SKILLS_DIR="$HOME/.hermes/skills"
MR_SKILL_DEST="$HERMES_SKILLS_DIR/productivity/morning-report"
MR_DELIVERY_TIME="08:00"                    # overwritten by step 8
MR_TIMEZONE="Asia/Ho_Chi_Minh"              # overwritten by step 8
DEV_MODE=false
[[ "${1:-}" == "--dev" ]] && DEV_MODE=true   # --dev also runs the unit tests
export HERMES_ENV_FILE

# Everything the customer sees is also written to the log they can send to
# support. Keys are masked before printing; nothing writes a raw key here.
exec > >(tee -a "$INSTALL_LOG") 2>&1

on_failure() {
    local line="$1"
    printf '\n'
    printf 'INSTALL FAILED (line %s).\n' "$line"
    printf 'Nothing is broken on this Mac — the install simply stopped part-way.\n'
    printf 'Two things to do:\n'
    printf '  1. Run the same command again. It picks up where it stopped and does not\n'
    printf '     ask again for anything already saved.\n'
    printf '  2. If it stops again, send this file to support: %s\n' "$INSTALL_LOG"
    printf '     (it contains no API keys — they are masked)\n'
}
trap 'on_failure "$LINENO"' ERR

# ── Source layout ──────────────────────────────────────────────────────
# Two ways this script runs: from a checkout (setup/install-mac.sh, libs beside
# it) or piped from curl (no files at all — download the source, which is needed
# anyway because the skills are copied out of it).
resolve_source_dir() {
    local self_dir=""
    if [[ -n "$MR_SOURCE_DIR" ]]; then
        printf '%s' "$MR_SOURCE_DIR"; return 0
    fi
    if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
        self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [[ -d "$self_dir/../skills/morning-report" ]]; then
            (cd "$self_dir/.." && pwd); return 0
        fi
    fi

    local dest="$HOME/.hermes/morning-report-src"
    printf 'Downloading the morning report files ...\n' >&2
    rm -rf "$dest"; mkdir -p "$dest"
    if ! curl -fsSL "$MR_REPO_TARBALL" | tar -xz --strip-components=1 -C "$dest"; then
        printf 'Could not download the installation files from:\n  %s\n' "$MR_REPO_TARBALL" >&2
        printf 'Check the internet connection, or ask support for the files and run\n' >&2
        printf 'setup/install-mac.sh from the downloaded folder instead.\n' >&2
        return 1
    fi
    printf '%s' "$dest"
}

SRC_DIR="$(resolve_source_dir)"
LIB_DIR="$SRC_DIR/setup/lib"
# Everything installed on the machine points at this copy, never at wherever the
# operator happened to run the script from: the watchdog's health check and the
# re-runnable add-on must not break the day someone deletes a Downloads folder.
CANON_SRC="$HOME/.hermes/morning-report-src"
# shellcheck source=lib/wizard-prompts.sh
source "$LIB_DIR/wizard-prompts.sh"
# shellcheck source=lib/validate-api-keys.sh
source "$LIB_DIR/validate-api-keys.sh"
# shellcheck source=lib/setup-launchd.sh
source "$LIB_DIR/setup-launchd.sh"
# shellcheck source=lib/setup-watchdog.sh
source "$LIB_DIR/setup-watchdog.sh"

PY="/usr/bin/python3"   # re-pointed by preflight if the system one is unusable

# ── Step 0: preflight ──────────────────────────────────────────────────
step_preflight() {
    say_step "Step 1 of 10 — checking this Mac"
    require_tty

    if [[ "$(uname -s)" != "Darwin" ]]; then
        say_err "This installer is for macOS. On an Ubuntu VPS use setup/setup_all_hermes.sh instead."
        exit 1
    fi

    local product_version major
    product_version="$(sw_vers -productVersion)"
    major="${product_version%%.*}"
    if (( major < 13 )); then
        say_err "macOS $product_version is too old. macOS 13 (Ventura) or newer is required."
        exit 1
    fi
    say_ok "macOS $product_version on $(uname -m)"

    # The morning report itself runs on the Python that ships with macOS — no
    # Homebrew, no pip (verified: all 5 test suites pass on /usr/bin/python3 3.9.6).
    if ! "$PY" --version >/dev/null 2>&1; then
        if command -v python3 >/dev/null 2>&1; then
            PY="$(command -v python3)"
        else
            say_err "python3 is missing. Run this command, click Install, wait for it to finish, then run the installer again:"
            say     "  xcode-select --install"
            exit 1
        fi
    fi
    say_ok "python3: $("$PY" --version 2>&1)"

    local free_kb
    free_kb="$(df -Pk "$HOME" | awk 'NR==2{print $4}')"
    if [[ "${free_kb:-0}" -lt 2097152 ]]; then
        say_err "Less than 2 GB of free disk space. Free some space and run the installer again."
        exit 1
    fi
    say_ok "Free disk space: $(( free_kb / 1048576 )) GB"

    if ! curl -s -o /dev/null --max-time 20 https://api.telegram.org; then
        say_err "Cannot reach the internet (api.telegram.org). Check the network and try again."
        exit 1
    fi
    say_ok "Internet connection works"

    if ! command -v ffmpeg >/dev/null 2>&1; then
        say_dim "  ffmpeg is not installed — the audio still works; step 10 installs ffmpeg for better joining."
    fi
}

# ── Step 1: Hermes CLI ─────────────────────────────────────────────────
step_install_hermes_cli() {
    say_step "Step 2 of 10 — installing the Hermes program"

    if command -v hermes >/dev/null 2>&1; then
        say_ok "Hermes is already installed ($(hermes --version 2>&1 | head -n 1)) — skipping."
        return 0
    fi

    # Deliberately only on a first install. The Hermes installer always runs its
    # own "install the gateway as a background service?" prompt, and on macOS the
    # yes-branch starts a second, unmanaged gateway process (`nohup hermes gateway`)
    # because it looks for systemd and finds none. Two gateways on one bot token =
    # Telegram 409 Conflict = dropped or duplicated messages. On a first install
    # ~/.hermes/.env holds no token yet, so that prompt does not appear.
    say "This downloads and installs Hermes. It takes a few minutes."
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup

    export PATH="$HOME/.local/bin:$PATH"
    hash -r
    if ! command -v hermes >/dev/null 2>&1; then
        say_err "Hermes was installed but the 'hermes' command is not available. Close Terminal, open it again, and re-run the installer."
        exit 1
    fi
    say_ok "Hermes installed: $(hermes --version 2>&1 | head -n 1)"
}

# ── Step 2: the wizard ─────────────────────────────────────────────────
step_collect_keys() {
    say_step "Step 3 of 10 — your accounts"
    env_file_init
    say "Four services are needed. Each one is free to sign up for; DeepSeek needs a"
    say "few dollars of prepaid balance (roughly a few dollars per year at 1-2 topics)."
    say "Paste each key when asked — it is checked immediately, so a wrong key is"
    say "caught now instead of at 8am tomorrow. Nothing is shown on screen as you type."

    collect_key TELEGRAM_BOT_TOKEN "Telegram bot token" \
        "Telegram > search @BotFather > /newbot > copy the token" validate_telegram_token
    if [[ -n "${TELEGRAM_BOT_USERNAME:-}" ]]; then
        say_ok "That token belongs to the bot @${TELEGRAM_BOT_USERNAME} — check that this is your bot."
    fi

    collect_key DEEPSEEK_API_KEY "DeepSeek API" "https://platform.deepseek.com" validate_deepseek_key
    collect_key EXA_API_KEY "Exa search" "https://exa.ai" validate_exa_key
    collect_key FIRECRAWL_API_KEY "Firecrawl page reader" "https://firecrawl.dev" validate_firecrawl_key
    collect_key BRAVE_SEARCH_API_KEY "Brave Search (optional backup)" \
        "https://brave.com/search/api" validate_brave_key optional
}

# ── Step 3: hermes setup ───────────────────────────────────────────────
step_hermes_setup() {
    say_step "Step 4 of 10 — connecting Hermes to Telegram and DeepSeek"

    if [[ -n "$(env_get TELEGRAM_BOT_TOKEN)" ]]; then
        say_ok "Hermes is already connected to your bot — skipping this wizard."
        return 0
    fi

    say "Hermes now runs its own setup screens. You will be asked for:"
    say "  1. the AI provider   -> choose ${C_BOLD}DeepSeek${C_RESET}, then paste the DeepSeek key you just entered"
    say "  2. the chat platform -> choose ${C_BOLD}Telegram${C_RESET}, then paste the bot token"
    say "  3. allowed users     -> your own Telegram user id (the wizard explains how to get it)"
    say "  4. home channel      -> the chat where the bot should send messages"
    say ""
    say "Both values are already on your clipboard-safe list above; paste the same ones."
    say_dim "  (These screens are not written to the install log, so the keys you paste stay out of it.)"
    pause_for_enter "Press Enter to start the Hermes setup screens..."

    hermes setup </dev/tty >/dev/tty 2>&1 || {
        say_err "The Hermes setup wizard did not finish. Run the installer again to retry it."
        exit 1
    }

    if [[ -z "$(env_get TELEGRAM_BOT_TOKEN)" ]]; then
        say_err "Telegram was not configured (no bot token was saved). Run the installer again and choose Telegram in the wizard."
        exit 1
    fi
    say_ok "Hermes is connected to Telegram."
}

# ── Step 4-5: skills + search keys ─────────────────────────────────────
step_install_skills() {
    say_step "Step 5 of 10 — installing the skills"

    mkdir -p "$HERMES_SKILLS_DIR/productivity"
    # Copy, never symlink: a symlink into a downloaded folder dies silently the
    # day the customer moves or deletes that folder.
    rsync -a --delete "$SRC_DIR/skills/morning-report/" "$MR_SKILL_DEST/"
    if [[ -L "$MR_SKILL_DEST" || ! -f "$MR_SKILL_DEST/SKILL.md" ]]; then
        say_err "The skill was not copied correctly to $MR_SKILL_DEST"
        exit 1
    fi
    say_ok "Skill installed at $MR_SKILL_DEST"

    # SOUL.md sends the user to `guided-setup` for anything to do with keys or
    # connecting Google, so the skill has to be here or "set this up for me"
    # lands on a skill that does not exist.
    rsync -a --delete "$SRC_DIR/skills/guided-setup/" "$HERMES_SKILLS_DIR/guided-setup/"
    if [[ ! -f "$HERMES_SKILLS_DIR/guided-setup/SKILL.md" ]]; then
        say_err "The setup skill was not copied correctly to $HERMES_SKILLS_DIR/guided-setup"
        exit 1
    fi
    say_ok "In-chat setup skill installed."

    if [[ -f "$HOME/.hermes/SOUL.md" ]]; then
        say_dim "  ~/.hermes/SOUL.md already exists — kept as it is."
    else
        cp "$SRC_DIR/SOUL.md" "$HOME/.hermes/SOUL.md"
        say_ok "Bot personality file installed."
    fi

    say_step "Step 6 of 10 — saving the search keys"
    env_set EXA_API_KEY "$EXA_API_KEY"
    env_set FIRECRAWL_API_KEY "$FIRECRAWL_API_KEY"
    [[ -n "${BRAVE_SEARCH_API_KEY:-}" ]] && env_set BRAVE_SEARCH_API_KEY "$BRAVE_SEARCH_API_KEY"
    say_ok "Saved to ~/.hermes/.env (readable only by you)."

    if [[ "$DEV_MODE" == "true" ]]; then
        say_dim "  --dev: running the unit tests"
        local t
        for t in "$SRC_DIR"/skills/morning-report/tests/test_*.py \
                 "$SRC_DIR"/skills/guided-setup/tests/test_*.py; do
            "$PY" "$t" || say_warn "  test failed: $(basename "$t")"
        done
    fi
}

# ── Step 8: topics + delivery time ─────────────────────────────────────
step_configure_report() {
    say_step "Step 8 of 10 — what the report should cover"

    local default_tz topic_count topic delivery_time report_language i
    default_tz="$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')"
    : "${default_tz:=Asia/Ho_Chi_Minh}"

    say "One report per topic, one delivery per day."
    say_dim "  1 or 2 topics stays inside the free limits of Exa and Firecrawl."
    local args=()
    while true; do
        topic_count="$(prompt_line "  How many topics?" "1")"
        [[ "$topic_count" =~ ^[1-9][0-9]*$ ]] && break
        say_err "  Enter a number, for example 1 or 2."
    done
    if (( topic_count > 2 )); then
        say_warn "  With $topic_count topics you may go over the Firecrawl free allowance"
        say_warn "  (about 1,000 page reads per month, 5-10 per report). Extra topics may cost money."
        prompt_yes_no "  Continue with $topic_count topics?" "no" || topic_count=2
    fi

    for (( i = 1; i <= topic_count; i++ )); do
        while true; do
            topic="$(prompt_line "  Topic $i (for example: AI news, gold price)")"
            [[ -n "$topic" ]] && break
            say_err "  A topic cannot be empty."
        done
        args+=(--add-topic "$topic")
    done

    while true; do
        delivery_time="$(prompt_line "  Delivery time, 24-hour clock" "08:00")"
        [[ "$delivery_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] && break
        say_err "  Use HH:MM, for example 08:00 or 17:30."
    done
    report_language="$(prompt_line "  Report language" "English")"

    MR_DELIVERY_TIME="$delivery_time"
    MR_TIMEZONE="$default_tz"

    "$PY" "$MR_SKILL_DEST/scripts/prepare_config.py" \
        "${args[@]}" --all-topics \
        --delivery-time "$delivery_time" \
        --timezone "$default_tz" \
        --report-language "$report_language" \
        --save --enable-cron >/dev/null
    say_ok "Configured: $topic_count topic(s), $delivery_time $default_tz, in $report_language."
}

# ── Step 9: acceptance through the real delivery path ──────────────────
# Running collect_sources.py by hand only proves the keys work. The product is
# "a report arrives on its own at 8am", so the test has to be: schedule a real
# cron a few minutes out, wait, and see it arrive unattended.
step_acceptance() {
    say_step "Step 9 of 10 — test delivery (about 15 minutes)"

    local test_time restore_time
    test_time="$(TZ="$MR_TIMEZONE" date -v+6M +%H:%M 2>/dev/null || true)"
    if [[ -z "$test_time" ]]; then
        say_warn "Could not work out a test time; skipping the automatic test."
        return 0
    fi
    restore_time="$MR_DELIVERY_TIME"

    say "The delivery time is moved to $test_time for one run, so you can watch a real"
    say "report arrive in Telegram without waiting until tomorrow morning."
    "$PY" "$MR_SKILL_DEST/scripts/prepare_config.py" \
        --all-topics --delivery-time "$test_time" --save --enable-cron >/dev/null

    local waited=0
    say_dim "  Waiting for the bot to send the report (open Telegram now). It fires at $test_time, then needs a few minutes to search, write and record."
    while (( waited < 900 )); do
        sleep 30
        waited=$(( waited + 30 ))
        printf '\r  %s seconds elapsed ... ' "$waited"
    done
    printf '\n'

    local delivered="no"
    if prompt_yes_no "  Did the report arrive in Telegram?" "yes"; then
        delivered="yes"
    fi

    "$PY" "$MR_SKILL_DEST/scripts/prepare_config.py" \
        --all-topics --delivery-time "$restore_time" --save --enable-cron >/dev/null
    say_ok "Delivery time set back to $restore_time."

    if [[ "$delivered" == "yes" ]]; then
        say_ok "Test delivery worked — the daily report is live."
    else
        say_warn "No report arrived. The rest of the install is fine, but this needs looking at."
        say     "  1. Run this command and send the result to support:  hermes-check"
        say     "  2. Also send this file:  $INSTALL_LOG"
        say     "  3. You can ask the bot in Telegram at any time: \"send report\""
    fi
}

# ── Step 10: the doc-convert add-on ────────────────────────────────────
# Chained, not suggested: both skills are part of the handover. Run as a
# subprocess so `set -e` inside it can never abort the morning-report install —
# Homebrew, Xcode CLT and LibreOffice are four new ways to fail and none of them
# may take the morning report down with them.
step_doc_addon() {
    say_step "Step 10 of 10 — document conversion (Word/PowerPoint/PDF)"

    local addon="$CANON_SRC/setup/install-doc-addon.sh"
    if [[ ! -f "$addon" ]]; then
        say_warn "install-doc-addon.sh not found — skipping document conversion."
        return 0
    fi

    if bash "$addon" --chained; then
        say_ok "Document conversion installed."
    else
        say_warn "Document conversion could not be installed (see the messages above)."
        say     "The morning report is not affected and will keep working."
        say     "To try again later, run:  bash $addon"
    fi
    return 0
}

verify_both_skills() {
    say_step "Checking the result"
    local ok=true

    if [[ -d "$MR_SKILL_DEST" && ! -L "$MR_SKILL_DEST" ]]; then
        say_ok "Morning report skill installed."
    else
        say_err "Morning report skill missing at $MR_SKILL_DEST"; ok=false
    fi

    if [[ -d "$HERMES_SKILLS_DIR/doc-convert" && ! -L "$HERMES_SKILLS_DIR/doc-convert" ]]; then
        say_ok "Document conversion skill installed."
    else
        say_warn "Document conversion skill not installed (the morning report still works)."
    fi

    hermes doctor >/dev/null 2>&1 && say_ok "Hermes reports no problems." \
        || say_warn "'hermes doctor' reported something — run hermes-check for details."

    bash "$CANON_SRC/setup/scripts/healthcheck_hermes.sh" || true

    [[ "$ok" == "true" ]]
}

print_done() {
    say ""
    say "${C_BOLD}Installation finished.${C_RESET}"
    say ""
    say "Every day at $MR_DELIVERY_TIME ($MR_TIMEZONE) the bot sends the report to Telegram."
    say ""
    say "Three things to know:"
    say "  * Leave this Mac ${C_BOLD}on and logged in${C_RESET}. After a restart, log in again —"
    say "    the bot does not run on the login screen."
    say "  * Something looks wrong? Run ${C_BOLD}hermes-check${C_RESET} in Terminal and send the result to support."
    say "  * Want the report right now? Message the bot: \"send report\"."
    say ""
    say "Full details: docs/limits-mac.md and docs/troubleshoot-mac.md"
    say "Install log: $INSTALL_LOG"
}

install_source_copy() {
    if [[ "$SRC_DIR" == "$CANON_SRC" ]]; then
        return 0
    fi
    mkdir -p "$CANON_SRC"
    rsync -a --exclude '.git' --exclude 'plans' "$SRC_DIR/" "$CANON_SRC/"
    say_dim "  Installation files kept at $CANON_SRC (used by the watchdog and the add-on)"
}

main() {
    say "${C_BOLD}Hermes morning report — macOS installer${C_RESET}"
    say_dim "A log of this install is kept at $INSTALL_LOG"

    step_preflight
    install_source_copy
    step_install_hermes_cli
    step_collect_keys
    step_hermes_setup
    step_install_skills

    say_step "Step 7 of 10 — keeping the bot running"
    setup_launchd_gateway
    prevent_system_sleep
    install_hermes_check_command "$CANON_SRC/setup/scripts/healthcheck_hermes.sh"

    step_configure_report
    step_acceptance
    # The watchdog goes live only now, deliberately. It runs on RunAtLoad and every
    # 15 minutes; installed before the test delivery it would see a machine with no
    # report yet (or with sleep still on, if the customer declined the sudo prompt),
    # restart the gateway in the middle of the acceptance test, and message the
    # customer "the bot is not working" while we are standing next to them.
    setup_watchdog "$CANON_SRC/setup/scripts/healthcheck_hermes.sh"
    step_doc_addon
    verify_both_skills || true
    print_done
}

main "$@"
