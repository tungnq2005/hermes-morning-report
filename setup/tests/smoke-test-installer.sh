#!/usr/bin/env bash
# Smoke-test the macOS installer libraries without installing anything and without
# touching the real ~/.hermes. Everything runs against a temporary HOME.
#
#   bash setup/tests/smoke-test-installer.sh
#
# Covers what can be checked off-machine: env file handling, key masking, every
# validator against the live API endpoints (with deliberately bad keys), the
# generated watchdog/hermes-check artifacts, the interpreter probe, and the
# healthcheck grace window. It does NOT install Hermes or deliver a report — see
# the NOT-RUN table in plans/260813-1639-mac-customer-installer/reports/.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SANDBOX="$(mktemp -d)"
FAILED=0
ok()   { printf '  PASS %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; FAILED=$((FAILED+1)); }

export HERMES_ENV_FILE="$SANDBOX/.hermes/.env"
source "$REPO/setup/lib/wizard-prompts.sh"
source "$REPO/setup/lib/validate-api-keys.sh"

echo "== wizard-prompts =="
env_file_init
[[ -f "$HERMES_ENV_FILE" ]] && ok "env_file_init creates the file" || bad "env_file_init"
[[ "$(stat -f '%Lp' "$HERMES_ENV_FILE")" == "600" ]] && ok "env file is 0600" || bad "env file perms"

env_set EXA_API_KEY "abc123"
[[ "$(env_get EXA_API_KEY)" == "abc123" ]] && ok "env_set/env_get round-trip" || bad "env_set/env_get"
env_set EXA_API_KEY "def|456&789"
[[ "$(env_get EXA_API_KEY)" == "def|456&789" ]] && ok "env_set survives sed metacharacters" || bad "env_set metachars"
[[ "$(grep -c '^EXA_API_KEY=' "$HERMES_ENV_FILE")" == "1" ]] && ok "env_set updates in place (no duplicate)" || bad "env_set duplicated the key"
env_set FIRECRAWL_API_KEY "fc-xyz"
[[ "$(env_get EXA_API_KEY)" == "def|456&789" && "$(env_get FIRECRAWL_API_KEY)" == "fc-xyz" ]] && ok "env_set keeps other keys" || bad "env_set lost a key"
[[ "$(env_get NOPE_KEY)" == "" ]] && ok "env_get returns empty for missing key" || bad "env_get missing"

masked="$(mask_secret "sk-1234567890abcdef")"
[[ "$masked" == *"cdef" && "$masked" != *"1234567890"* ]] && ok "mask_secret hides all but last 4 ($masked)" || bad "mask_secret ($masked)"
[[ "$(mask_secret "ab")" == "****" ]] && ok "mask_secret handles short values" || bad "mask_secret short"

echo "== validate-api-keys (offline / bad-key paths) =="
if ! validate_telegram_token "not-a-token" 2>/dev/null; then ok "telegram: rejects a malformed token without a network call"; else bad "telegram malformed"; fi
if ! validate_telegram_token "123456789:AAEabcdefghijklmnopqrstuvwxyz0123456" 2>/dev/null; then ok "telegram: rejects a well-formed but fake token"; else bad "telegram fake token accepted"; fi
if ! validate_deepseek_key "sk-bogus-key-for-testing" 2>/dev/null; then ok "deepseek: rejects a bogus key"; else bad "deepseek bogus accepted"; fi
if ! validate_exa_key "bogus" 2>/dev/null; then ok "exa: rejects a bogus key"; else bad "exa bogus accepted"; fi
if ! validate_firecrawl_key "fc-bogus" 2>/dev/null; then ok "firecrawl: rejects a bogus key"; else bad "firecrawl bogus accepted"; fi
if ! validate_brave_key "bogus" 2>/dev/null; then ok "brave: rejects a bogus key"; else bad "brave bogus accepted"; fi

echo "== setup-watchdog (generated artifacts) =="
(
    export HOME="$SANDBOX"
    mkdir -p "$HOME/.hermes"
    source "$REPO/setup/lib/wizard-prompts.sh"
    source "$REPO/setup/lib/setup-watchdog.sh"
    _write_watchdog_script "$REPO/setup/scripts/healthcheck_hermes.sh"
    _write_watchdog_plist
    _install_hermes_check "$REPO/setup/scripts/healthcheck_hermes.sh"
    /bin/bash -n "$HOME/.hermes/watchdog/morning-report-watchdog.sh" || exit 1
    /bin/bash -n "$HOME/.local/bin/hermes-check" || exit 1
    grep -q "$REPO/setup/scripts/healthcheck_hermes.sh" "$HOME/.hermes/watchdog/morning-report-watchdog.sh" || exit 1
    grep -q '__HEALTHCHECK_PATH__' "$HOME/.hermes/watchdog/morning-report-watchdog.sh" && exit 1
    plutil -lint "$HOME/Library/LaunchAgents/ai.hermes.morningreport.watchdog.plist" >/dev/null || exit 1
) && ok "watchdog script + hermes-check are valid bash, plist passes plutil" || bad "watchdog artifacts"

(
    export HOME="$SANDBOX"
    out="$(bash "$SANDBOX/.local/bin/hermes-check" 2>&1)"
    printf '%s' "$out" | grep -q "===== end =====" || exit 1
    printf '%s' "$out" | grep -q "morning-report MISSING" || exit 1
    # It must never print a secret value, only key names.
    printf '%s' "$out" | grep -q "def|456&789" && exit 1
    exit 0
) && ok "hermes-check runs end-to-end and leaks no key values" || bad "hermes-check run"

echo "== watchdog behaviour with a stub healthcheck =="
(
    export HOME="$SANDBOX"
    stub="$SANDBOX/healthcheck-stub.sh"
    printf '#!/usr/bin/env bash\nprintf %s\n"{\\"ok\\":true,\\"problems\\":[]}"\nexit 0\n' > "$stub"
    source "$REPO/setup/lib/wizard-prompts.sh"
    source "$REPO/setup/lib/setup-watchdog.sh"
    _write_watchdog_script "$stub"
    bash "$SANDBOX/.hermes/watchdog/morning-report-watchdog.sh"
) && ok "watchdog exits 0 and stays quiet when healthy" || bad "watchdog healthy path"

echo "== watchdog: sleep-only problem must not raise a false alarm =="
(
    export HOME="$SANDBOX"
    mkdir -p "$SANDBOX/stubbin"
    # No real restarts, no 60s wait, and no ~/.hermes/.env so send_telegram cannot
    # reach the network — it just logs "cannot alert".
    printf '#!/bin/bash\nexit 0\n' > "$SANDBOX/stubbin/launchctl"
    printf '#!/bin/bash\nexit 0\n' > "$SANDBOX/stubbin/sleep"
    chmod +x "$SANDBOX/stubbin/launchctl" "$SANDBOX/stubbin/sleep"
    export PATH="$SANDBOX/stubbin:$PATH"

    stub="$SANDBOX/healthcheck-sleep.sh"
    printf '#!/usr/bin/env bash\necho %s\nexit 1\n' \
        "'{\"ok\":false,\"problems\":[\"machine_can_sleep:30\"]}'" > "$stub"
    source "$REPO/setup/lib/wizard-prompts.sh"
    source "$REPO/setup/lib/setup-watchdog.sh"
    _write_watchdog_script "$stub"
    rm -f "$SANDBOX/.hermes/.watchdog-alerted" "$SANDBOX/.hermes/.watchdog-sleep-alerted"
    bash "$SANDBOX/.hermes/watchdog/morning-report-watchdog.sh" || exit 1   # must exit 0
    [[ -f "$SANDBOX/.hermes/.watchdog-sleep-alerted" ]] || exit 1           # advisory sent once
    [[ -f "$SANDBOX/.hermes/.watchdog-alerted" ]] && exit 1                 # NOT "bot is broken"
    grep -q "kickstart" "$SANDBOX/.hermes/logs/watchdog.log" && exit 1      # no restart attempted
    exit 0
) && ok "sleep-only: advisory once, no restart, no false 'bot is not working'" || bad "watchdog sleep classification"

echo "== watchdog: a real failure still alerts =="
(
    export HOME="$SANDBOX"
    export PATH="$SANDBOX/stubbin:$PATH"
    stub="$SANDBOX/healthcheck-dead.sh"
    printf '#!/usr/bin/env bash\necho %s\nexit 1\n' \
        "'{\"ok\":false,\"problems\":[\"gateway_not_running\",\"machine_can_sleep:30\"]}'" > "$stub"
    source "$REPO/setup/lib/wizard-prompts.sh"
    source "$REPO/setup/lib/setup-watchdog.sh"
    _write_watchdog_script "$stub"
    rm -f "$SANDBOX/.hermes/.watchdog-alerted" "$SANDBOX/.hermes/.watchdog-sleep-alerted"
    bash "$SANDBOX/.hermes/watchdog/morning-report-watchdog.sh" && exit 1   # must exit non-zero
    [[ -f "$SANDBOX/.hermes/.watchdog-alerted" ]] || exit 1
    grep -q "still unhealthy after restart" "$SANDBOX/.hermes/logs/watchdog.log" || exit 1
    exit 0
) && ok "gateway down: restart attempted, then one alert" || bad "watchdog critical path"

echo "== install-doc-addon: resolve_skill_python =="
(
    export HOME="$SANDBOX"
    mkdir -p "$HOME/Library/LaunchAgents" "$SANDBOX/fakevenv/bin"
    printf '#!/bin/sh\necho fake\n' > "$SANDBOX/fakevenv/bin/python3"
    chmod +x "$SANDBOX/fakevenv/bin/python3"
    cat > "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin</string>
        <key>VIRTUAL_ENV</key>
        <string>$SANDBOX/fakevenv</string>
    </dict>
</dict>
</plist>
PLIST
    resolve_skill_python() { :; }
    eval "$(sed -n '/^resolve_skill_python()/,/^}/p' "$REPO/setup/install-doc-addon.sh")"
    got="$(resolve_skill_python)"
    [[ "$got" == "$SANDBOX/fakevenv/bin/python3" ]] || { echo "    got: $got"; exit 1; }
) && ok "resolve_skill_python reads VIRTUAL_ENV out of the gateway plist" || bad "resolve_skill_python"

echo "== healthcheck: install grace window =="
(
    export HOME="$SANDBOX"
    mkdir -p "$SANDBOX/.hermes"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$SANDBOX/.hermes/.installed-at"
    out="$(OC_HOME="$SANDBOX" bash "$REPO/setup/scripts/healthcheck_hermes.sh")"
    printf '%s' "$out" | grep -q '"install_grace":true' || exit 1
    printf '%s' "$out" | grep -q 'no_recent_report_26h' && exit 1
    exit 0
) && ok "fresh install suppresses the no-report-in-26h alarm" || bad "grace window"

(
    export HOME="$SANDBOX"
    rm -f "$SANDBOX/.hermes/.installed-at"
    out="$(OC_HOME="$SANDBOX" bash "$REPO/setup/scripts/healthcheck_hermes.sh")"
    printf '%s' "$out" | grep -q 'no_recent_report_26h' || exit 1
) && ok "without the marker the no-report alarm fires" || bad "grace window off"

rm -rf "$SANDBOX"
echo
if [[ $FAILED -eq 0 ]]; then echo "ALL SMOKE TESTS PASSED"; else echo "$FAILED FAILED"; fi
exit $FAILED
