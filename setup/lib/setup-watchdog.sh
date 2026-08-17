#!/usr/bin/env bash
# Install the morning-report watchdog: a LaunchAgent that runs every 15 minutes,
# checks the system with healthcheck_hermes.sh, tries a restart, and — if that
# fails — messages Telegram directly with curl. Sourced by install-mac.sh.
#
# Why outside Hermes: a process cannot report its own death. Anything that alerts
# through the gateway is silent exactly when it matters. With no remote access
# (customer's decision), this Telegram message is the only way anyone learns the
# bot has stopped.
#
# Why healthcheck instead of pgrep: pgrep only catches a *dead* gateway. On a Mac
# running for months the likelier failure is a *wedged* one — process alive, long
# poll stalled, no reports. healthcheck_hermes.sh already tests "a report in the
# last 26h", which catches that; pgrep would pass forever while nothing arrives.

WATCHDOG_LABEL="ai.hermes.morningreport.watchdog"
WATCHDOG_DIR="$HOME/.hermes/watchdog"
WATCHDOG_SCRIPT="$WATCHDOG_DIR/morning-report-watchdog.sh"
WATCHDOG_PLIST="$HOME/Library/LaunchAgents/${WATCHDOG_LABEL}.plist"

_write_watchdog_script() {
    local healthcheck_path="$1"
    mkdir -p "$WATCHDOG_DIR"
    cat >"$WATCHDOG_SCRIPT" <<'WATCHDOG_EOF'
#!/usr/bin/env bash
# Installed by install-mac.sh — do not edit by hand; a re-run overwrites it.
# Runs every 15 minutes from launchd. Never writes the bot token anywhere.
set -uo pipefail

HEALTHCHECK="__HEALTHCHECK_PATH__"
ENV_FILE="$HOME/.hermes/.env"
STATE_DIR="$HOME/.hermes"
ALERTED_MARKER="$STATE_DIR/.watchdog-alerted"
SLEEP_ALERTED_MARKER="$STATE_DIR/.watchdog-sleep-alerted"
LOG="$STATE_DIR/logs/watchdog.log"
GATEWAY_LABEL="ai.hermes.gateway"

mkdir -p "$STATE_DIR/logs"
log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >>"$LOG"; }

# gui/$UID normally, user/$UID sometimes — probe like Hermes does instead of
# assuming, or a kickstart aimed at the wrong domain silently does nothing.
gateway_domain() {
    local uid; uid="$(id -u)"
    if launchctl print "gui/$uid/$GATEWAY_LABEL" >/dev/null 2>&1; then printf 'gui/%s' "$uid"; return; fi
    if launchctl print "user/$uid/$GATEWAY_LABEL" >/dev/null 2>&1; then printf 'user/%s' "$uid"; return; fi
    printf 'gui/%s' "$uid"
}

read_env() {  # read_env KEY — value only, never logged
    [[ -f "$ENV_FILE" ]] || return 0
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed 's/^"\(.*\)"$/\1/'
}

send_telegram() {  # send_telegram "<text>"
    local token chat_id
    token="$(read_env TELEGRAM_BOT_TOKEN)"
    # The home channel is the chat hermes setup was pointed at; fall back to the
    # first allowed user (a private-chat user id is a valid chat_id).
    chat_id="$(read_env TELEGRAM_HOME_CHANNEL)"
    [[ -z "$chat_id" ]] && chat_id="$(read_env TELEGRAM_ALLOWED_USERS | cut -d, -f1 | tr -d ' ')"
    if [[ -z "$token" || -z "$chat_id" ]]; then
        log "cannot alert: TELEGRAM_BOT_TOKEN or chat id missing from .env"
        return 1
    fi
    curl -s -o /dev/null --max-time 20 \
        -X POST "https://api.telegram.org/bot${token}/sendMessage" \
        --data-urlencode "chat_id=${chat_id}" \
        --data-urlencode "text=$1" \
        --data-urlencode "disable_notification=false" \
        >/dev/null 2>&1
}

run_healthcheck() {  # echoes the JSON summary; exit status 0 = healthy
    bash "$HEALTHCHECK" 2>/dev/null
}

problems_of() {  # extract the problems array from the healthcheck JSON
    printf '%s' "$1" | sed -n 's/.*"problems":\[\(.*\)\].*/\1/p' | tr -d '"'
}

# Problems that mean the BOT is broken, as opposed to the machine being
# misconfigured. `machine_can_sleep` is real and worth telling someone about, but
# restarting the gateway cannot fix it and "the bot is not working" would be a lie —
# it is running fine, it will just be suspended the next time the Mac sleeps.
critical_problems_of() {
    printf '%s' "$(problems_of "$1")" | tr ',' '\n' \
        | grep -v '^machine_can_sleep' | grep -v '^$' | tr '\n' ' '
}

first_output="$(run_healthcheck)"; first_status=$?

if [[ $first_status -eq 0 ]]; then
    if [[ -f "$ALERTED_MARKER" ]]; then
        rm -f "$ALERTED_MARKER"
        log "recovered: $first_output"
        send_telegram "$(hostname -s): the morning report bot is working again."
    fi
    rm -f "$SLEEP_ALERTED_MARKER"
    exit 0
fi

log "unhealthy: $first_output"

if [[ -z "$(critical_problems_of "$first_output")" ]]; then
    # Only the sleep setting is wrong: no restart, one plain-English notice.
    if [[ ! -f "$SLEEP_ALERTED_MARKER" ]]; then
        : >"$SLEEP_ALERTED_MARKER"
        send_telegram "$(hostname -s): the Mac is allowed to sleep again. The bot works now, but reports stop whenever the Mac sleeps. Fix: open Terminal and run  sudo pmset -a sleep 0 disksleep 0"
    fi
    exit 0
fi

# One restart attempt through launchd. kickstart -k restarts the existing job;
# never start a second process — Telegram allows one long-poller per bot token.
launchctl kickstart -k "$(gateway_domain)/${GATEWAY_LABEL}" >>"$LOG" 2>&1 \
    || log "kickstart failed (job may not be loaded)"
sleep 60

second_output="$(run_healthcheck)"; second_status=$?
if [[ $second_status -eq 0 || -z "$(critical_problems_of "$second_output")" ]]; then
    log "restart fixed it: $second_output"
    exit 0
fi

log "still unhealthy after restart: $second_output"

# Alert once per incident, not every 15 minutes.
if [[ -f "$ALERTED_MARKER" ]]; then
    exit 1
fi
: >"$ALERTED_MARKER"
send_telegram "$(hostname -s): the morning report bot is not working ($(critical_problems_of "$second_output")). Restarting it did not help. Run hermes-check in Terminal and send the result to support."
exit 1
WATCHDOG_EOF

    # Substitute the healthcheck path into the heredoc (kept quoted above so the
    # watchdog's own $variables survive verbatim).
    local tmp
    tmp="$(mktemp)"
    sed "s|__HEALTHCHECK_PATH__|${healthcheck_path}|" "$WATCHDOG_SCRIPT" >"$tmp"
    cat "$tmp" >"$WATCHDOG_SCRIPT"
    rm -f "$tmp"
    chmod 700 "$WATCHDOG_SCRIPT"
}

_write_watchdog_plist() {
    mkdir -p "$HOME/Library/LaunchAgents"
    cat >"$WATCHDOG_PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${WATCHDOG_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WATCHDOG_SCRIPT}</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${HOME}/.hermes/logs/watchdog.out.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/.hermes/logs/watchdog.error.log</string>
</dict>
</plist>
PLIST_EOF
}

# Install a small `hermes-check` command: one copy-pasteable block for support.
# Critical because there is no remote access — this is the only diagnostic channel.
_install_hermes_check() {
    local healthcheck_path="$1" bin_dir="$HOME/.local/bin"
    mkdir -p "$bin_dir"
    cat >"$bin_dir/hermes-check" <<CHECK_EOF
#!/usr/bin/env bash
# Installed by install-mac.sh. Prints one block to copy and send to support.
# Contains no API keys or tokens — only key names, never values.
set -uo pipefail
export PATH="\$HOME/.local/bin:\$PATH"
echo "===== morning report check ====="
echo "date:        \$(date)"
echo "machine:     \$(hostname -s)  macOS \$(sw_vers -productVersion)  \$(uname -m)"
echo "hermes:      \$(command -v hermes >/dev/null 2>&1 && hermes --version 2>&1 | head -n 1 || echo 'NOT INSTALLED')"
echo "gateway pid: \$(pgrep -fl gateway 2>/dev/null | grep -c 'hermes_cli.main.* gateway' || true)"
echo "sleep:       \$(pmset -g custom 2>/dev/null | grep -E '^[[:space:]]*sleep' | head -n 1 | tr -s ' ')"
echo "skills:      \$(ls -d "\$HOME/.hermes/skills/productivity/morning-report" 2>/dev/null || echo 'morning-report MISSING')"
echo "             \$(ls -d "\$HOME/.hermes/skills/doc-convert" 2>/dev/null || echo 'doc-convert MISSING')"
echo "env keys:    \$(cut -d= -f1 "\$HOME/.hermes/.env" 2>/dev/null | sort | tr '\n' ' ')"
echo "healthcheck: "
bash "${healthcheck_path}" 2>&1 | tail -n 3
echo "last reports:"
ls -t "\$HOME/.hermes/skills/productivity/morning-report/state/history" 2>/dev/null | head -n 3 || echo "  none yet"
echo "gateway log (last 15 lines):"
tail -n 15 "\$HOME/.hermes/logs/gateway.error.log" 2>/dev/null || echo "  no log"
echo "watchdog log (last 5 lines):"
tail -n 5 "\$HOME/.hermes/logs/watchdog.log" 2>/dev/null || echo "  no log"
echo "===== end ====="
CHECK_EOF
    chmod 755 "$bin_dir/hermes-check"
}

# Installed on its own, before the watchdog: the acceptance test in step 9 tells the
# customer to run `hermes-check` if no report arrives, so the command has to exist by
# then even though the watchdog LaunchAgent starts later.
install_hermes_check_command() {
    _install_hermes_check "$1"
    say_ok "Installed the 'hermes-check' command (run it in Terminal when something looks wrong)."
}

setup_watchdog() {
    local healthcheck_path="$1"

    say_step "Installing the watchdog (checks the bot every 15 minutes)"

    if [[ ! -f "$healthcheck_path" ]]; then
        say_err "Health check script not found at $healthcheck_path"
        return 1
    fi

    _write_watchdog_script "$healthcheck_path"
    _write_watchdog_plist
    _install_hermes_check "$healthcheck_path"

    # bootout first so a re-run reloads the current definition instead of failing
    # with "service already loaded". Boot it out of both domains — a previous run
    # may have landed in either.
    launchctl bootout "gui/$(id -u)/${WATCHDOG_LABEL}" >/dev/null 2>&1 || true
    launchctl bootout "user/$(id -u)/${WATCHDOG_LABEL}" >/dev/null 2>&1 || true
    if launchctl bootstrap "gui/$(id -u)" "$WATCHDOG_PLIST" >/dev/null 2>&1 \
       || launchctl bootstrap "user/$(id -u)" "$WATCHDOG_PLIST" >/dev/null 2>&1; then
        say_ok "Watchdog installed. If the bot stops, it restarts it and messages you on Telegram."
    else
        say_warn "Could not load the watchdog into launchd. The bot still works, but nobody is watching it."
        say_dim  "  Retry later with: launchctl bootstrap gui/\$(id -u) $WATCHDOG_PLIST"
    fi
    say_ok "Installed the 'hermes-check' command (run it in Terminal when something looks wrong)."
    return 0
}
