#!/usr/bin/env bash
# Stand up the Hermes gateway as a macOS LaunchAgent. Sourced by install-mac.sh.
#
# WHAT THIS DOES NOT DO, ON PURPOSE (verified against upstream hermes_cli/gateway.py,
# see plans/260813-1639-mac-customer-installer/reports/verify-mac-260813.md):
#
#   * It does not write a plist. `hermes gateway install` writes the canonical one
#     at ~/Library/LaunchAgents/ai.hermes.gateway.plist. Telegram allows exactly one
#     long-poller per bot token, so a second plist means 409 Conflict and
#     dropped/duplicated messages.
#   * It does not patch KeepAlive. Upstream already emits `<key>KeepAlive</key><true/>`
#     (the unconditional boolean form), and `launchd_plist_is_current()` rewrites any
#     hand-edited plist on the next install/start — a patch would be reverted anyway.
#   * It does not fall back to `launchctl load -w`. Upstream's bootstrap already
#     retries with bootout-and-retry, waits for registration to be confirmed by
#     `launchctl list`, and degrades to a detached process if the domain is
#     unmanageable. Legacy `load` on top of that risks a duplicate registration.
#
# What is left for us: run it, notice the degraded fallback, and prove exactly one
# gateway process is alive.

GATEWAY_LABEL="ai.hermes.gateway"
GATEWAY_PLIST="$HOME/Library/LaunchAgents/${GATEWAY_LABEL}.plist"
GATEWAY_UNSUPPORTED_MARKER="$HOME/.hermes/.gateway-launchd-unsupported"

# Which launchd domain actually holds a label. Upstream probes rather than assumes
# (`_launchd_domain()`, gateway.py:3809): `gui/$UID` is the normal answer for a
# logged-in session, but a service can end up in `user/$UID`. Hardcoding gui/ would
# make an otherwise healthy agent look "not loaded" — and make the watchdog alert
# about a bot that is running fine.
launchd_domain_for() {
    local label="$1" uid
    uid="$(id -u)"
    if launchctl print "gui/$uid/$label" >/dev/null 2>&1; then
        printf 'gui/%s' "$uid"; return 0
    fi
    if launchctl print "user/$uid/$label" >/dev/null 2>&1; then
        printf 'user/%s' "$uid"; return 0
    fi
    printf 'gui/%s' "$uid"   # not loaded anywhere: gui is the target to bootstrap into
}

# Count live gateway processes. Two spellings must both be caught: the LaunchAgent
# runs `<venv>/python -m hermes_cli.main gateway run --replace`, while a stray
# started by the Hermes installer's own prompt runs `hermes gateway` (see A8 in the
# verification report). `grep -v` drops our own tooling — the watchdog and
# short-lived `hermes gateway install|status` calls are not long-pollers.
gateway_pid_count() {
    pgrep -fl gateway 2>/dev/null \
        | grep -E "(hermes_cli\.main([[:space:]]+--profile[[:space:]]+[^[:space:]]+)?[[:space:]]+gateway|/hermes[[:space:]]+gateway|^[0-9]+[[:space:]]+hermes[[:space:]]+gateway)" \
        | grep -Ev "watchdog|gateway (install|status|stop|start|setup)" \
        | wc -l | tr -d ' '
}

# Wait until exactly one gateway process is alive (or the timeout expires).
# Echoes the final count.
gateway_wait_for_single_pid() {
    local deadline=$(( SECONDS + ${1:-60} )) count=0
    while (( SECONDS < deadline )); do
        count="$(gateway_pid_count)"
        [[ "$count" == "1" ]] && break
        sleep 3
    done
    printf '%s' "$count"
}

setup_launchd_gateway() {
    local count

    say_step "Installing the gateway as a background service (LaunchAgent)"

    if ! command -v hermes >/dev/null 2>&1; then
        say_err "The 'hermes' command is not on PATH — cannot install the service."
        return 1
    fi

    # Idempotent by design: with the plist already present and current, upstream
    # prints "Service already installed"; if it drifted, upstream repairs it.
    hermes gateway install || {
        say_err "'hermes gateway install' failed. See ~/.hermes/logs/gateway.error.log"
        return 1
    }

    if [[ ! -f "$GATEWAY_PLIST" ]]; then
        say_err "Expected the service definition at $GATEWAY_PLIST but it is not there."
        return 1
    fi
    say_ok "Service definition: $GATEWAY_PLIST"

    # `install` bootstraps the agent and RunAtLoad starts it. If something had
    # stopped it earlier (previous run, manual stop), start it explicitly.
    if [[ "$(gateway_pid_count)" == "0" ]]; then
        hermes gateway start || say_warn "'hermes gateway start' reported a problem — checking the process anyway."
    fi

    count="$(gateway_wait_for_single_pid 90)"

    if [[ -f "$GATEWAY_UNSUPPORTED_MARKER" ]]; then
        say_warn "macOS would not let launchd supervise the gateway, so Hermes started it as a plain background process."
        say_warn "It is running now, but it will NOT come back by itself after a restart or a logout."
        say_dim  "  Report this to support with the file ~/.hermes/.gateway-launchd-unsupported"
    fi

    case "$count" in
        1)
            say_ok "Gateway running — exactly one process, as required."
            ;;
        0)
            say_err "The gateway is not running. Check ~/.hermes/logs/gateway.error.log"
            return 1
            ;;
        *)
            say_err "$count gateway processes are running. Telegram allows only one per bot token —"
            say_err "with two, messages get duplicated or silently dropped."
            say_dim  "  Fix: launchctl bootout $(launchd_domain_for "$GATEWAY_LABEL")/${GATEWAY_LABEL} ; pkill -f 'hermes_cli.main.* gateway' ; hermes gateway start"
            return 1
            ;;
    esac

    # The healthcheck suppresses its "no report in the last 26h" alarm for the
    # first 26 hours; without this marker a brand-new install looks broken.
    mkdir -p "$HOME/.hermes"
    date -u +"%Y-%m-%dT%H:%M:%SZ" >"$HOME/.hermes/.installed-at"
    return 0
}

# ── Sleep prevention ───────────────────────────────────────────────────
# An always-on Mac that sleeps is the single most common way for reports to stop
# arriving with no error at all: launchd suspends the gateway with the machine.
prevent_system_sleep() {
    say_step "Stopping this Mac from going to sleep"
    say "The report is produced by a program running on this Mac at the delivery time."
    say "If macOS puts the Mac to sleep, that program is paused and no report is sent —"
    say "with no error message anywhere. Turning off sleep needs your macOS password once."
    say_dim "  Command: sudo pmset -a sleep 0 disksleep 0   (the display can still turn off)"
    say ""

    if ! prompt_yes_no "Turn off sleep now (recommended)?" "yes"; then
        say_warn "Skipped. Reports will stop arriving whenever this Mac sleeps."
        say_dim  "  Run it later with: sudo pmset -a sleep 0 disksleep 0"
        return 0
    fi

    if ! sudo pmset -a sleep 0 disksleep 0; then
        say_warn "Could not change the sleep settings (wrong password, or the setting is managed by your organisation)."
        return 0
    fi
    # Screen off is fine and saves the panel; only machine sleep is fatal.
    sudo pmset -a displaysleep 10 >/dev/null 2>&1 || true

    # Read back from `custom`, not plain `pmset -g`: the latter reports the
    # effective value including transient assertions (caffeinate, sharingd),
    # so it can print "sleep 0" while the stored setting is still 30.
    if pmset -g custom 2>/dev/null | grep -E '^[[:space:]]*sleep[[:space:]]+0' >/dev/null; then
        say_ok "Sleep is off. The Mac stays awake (the screen may still turn off)."
    else
        say_warn "The setting did not take effect. Check System Settings > Energy / Battery."
    fi
    return 0
}
