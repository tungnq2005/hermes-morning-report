#!/usr/bin/env bash
# English prompt + logging helpers for the macOS installer (install-mac.sh,
# install-doc-addon.sh). Sourced, never executed directly.
#
# Everything reads from /dev/tty, not stdin: the installer is meant to be run as
# `curl -fsSL .../install-mac.sh | bash`, so stdin is the pipe and a plain `read`
# would consume the script itself.
#
# Secrets never reach stdout or the log — see mask_secret().

# ── Output ─────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_RESET=$'\033[0m'
else
    C_BOLD=""; C_DIM=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_RESET=""
fi

say()      { printf '%s\n' "$*"; }
say_step() { printf '\n%s==> %s%s\n' "$C_BOLD" "$*" "$C_RESET"; }
say_ok()   { printf '%s  OK  %s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
say_warn() { printf '%s WARN %s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
say_err()  { printf '%s FAIL %s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
say_dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_RESET"; }

# Print a value with all but the last 4 characters replaced by dots. Use this
# for anything key-shaped: the installer's whole output is tee'd to a log file
# the customer emails to support.
mask_secret() {
    local value="$1"
    local length=${#value}
    if (( length <= 4 )); then
        printf '****'
    else
        printf '%s%s' "$(printf '.%.0s' $(seq 1 $(( length > 24 ? 20 : length - 4 ))))" "${value: -4}"
    fi
}

# ── Input (always /dev/tty) ────────────────────────────────────────────
have_tty() { (: </dev/tty) 2>/dev/null; }

require_tty() {
    if ! have_tty; then
        say_err "No terminal available. Run this installer from Terminal, not from a script or CI."
        exit 1
    fi
}

# prompt_line "<question>" [default]  -> echoes the answer
prompt_line() {
    local question="$1" default="${2:-}" answer=""
    if [[ -n "$default" ]]; then
        printf '%s [%s]: ' "$question" "$default" >/dev/tty
    else
        printf '%s: ' "$question" >/dev/tty
    fi
    IFS= read -r answer </dev/tty || true
    printf '%s' "${answer:-$default}"
}

# prompt_secret "<question>"  -> echoes the answer, never echoes keystrokes
prompt_secret() {
    local question="$1" answer=""
    printf '%s: ' "$question" >/dev/tty
    IFS= read -rs answer </dev/tty || true
    printf '\n' >/dev/tty
    printf '%s' "$answer"
}

# prompt_yes_no "<question>" [yes|no]  -> exit status 0 for yes
prompt_yes_no() {
    local question="$1" default="${2:-yes}" answer=""
    local hint="[Y/n]"
    [[ "$default" == "no" ]] && hint="[y/N]"
    while true; do
        printf '%s %s ' "$question" "$hint" >/dev/tty
        IFS= read -r answer </dev/tty || true
        answer="${answer:-$default}"
        case "$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *) printf 'Please answer y or n.\n' >/dev/tty ;;
        esac
    done
}

pause_for_enter() {
    printf '%s' "${1:-Press Enter to continue...}" >/dev/tty
    IFS= read -r _ </dev/tty || true
}

# ── ~/.hermes/.env access ──────────────────────────────────────────────
# HERMES_ENV_FILE is exported by install-mac.sh; default here keeps the libs
# usable standalone (e.g. install-doc-addon.sh run on its own).
: "${HERMES_ENV_FILE:=$HOME/.hermes/.env}"

env_file_init() {
    mkdir -p "$(dirname "$HERMES_ENV_FILE")"
    touch "$HERMES_ENV_FILE"
    chmod 600 "$HERMES_ENV_FILE"
}

# env_get KEY -> echoes the stored value ("" when absent)
env_get() {
    local key="$1"
    [[ -f "$HERMES_ENV_FILE" ]] || return 0
    sed -n "s/^${key}=//p" "$HERMES_ENV_FILE" | tail -n 1 | sed 's/^"\(.*\)"$/\1/'
}

# env_set KEY VALUE — idempotent update-or-append, never logs the value.
env_set() {
    local key="$1" value="$2" tmp
    env_file_init
    if grep -q "^${key}=" "$HERMES_ENV_FILE" 2>/dev/null; then
        tmp="$(mktemp)"
        # No `sed -i` — BSD sed needs an argument for it, and a value containing
        # `|` or `&` would corrupt an in-place substitution anyway.
        grep -v "^${key}=" "$HERMES_ENV_FILE" >"$tmp" || true
        printf '%s=%s\n' "$key" "$value" >>"$tmp"
        cat "$tmp" >"$HERMES_ENV_FILE"
        rm -f "$tmp"
    else
        printf '%s=%s\n' "$key" "$value" >>"$HERMES_ENV_FILE"
    fi
    chmod 600 "$HERMES_ENV_FILE"
}
