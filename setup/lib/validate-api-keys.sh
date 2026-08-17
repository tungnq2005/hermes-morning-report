#!/usr/bin/env bash
# Per-key validation for the macOS installer. Sourced by install-mac.sh.
#
# Every function: exit 0 = key works, non-zero = key rejected + an English reason
# on stderr. Endpoints and headers mirror exactly what the skill calls at report
# time (skills/morning-report/scripts/collect_sources.py) — validating a
# different endpoint would prove nothing about tomorrow's 8am run.
#
# Keys are passed as arguments, never printed. `curl --data @-` reads bodies from
# stdin so nothing key-shaped lands in the process table either.

VALIDATE_TIMEOUT="${VALIDATE_TIMEOUT:-25}"

# Last bot username seen by validate_telegram_token, for the confirmation print.
TELEGRAM_BOT_USERNAME=""

_http_status() {  # _http_status <curl args...> -> echoes the HTTP status code
    curl -s -o /dev/null -w '%{http_code}' \
        --max-time "$VALIDATE_TIMEOUT" "$@" 2>/dev/null || printf '000'
}

_explain_status() {  # _explain_status <service> <code>
    local service="$1" code="$2"
    case "$code" in
        000) say_err "$service: could not be reached. Check the internet connection and try again." ;;
        # 422 is what Brave answers for an invalid subscription token; 400 covers
        # a key pasted with stray characters. Both mean "wrong key", not "outage".
        400|401|403|422) say_err "$service: the key was rejected (HTTP $code). Copy it again from the dashboard." ;;
        402) say_err "$service: the account has no credit left (HTTP 402). Top it up, then retry." ;;
        429) say_err "$service: rate limit or quota reached (HTTP 429). Wait a minute, then retry." ;;
        5*) say_err "$service: the service is having problems (HTTP $code). This is not your key — retry shortly." ;;
        *) say_err "$service: unexpected response (HTTP $code)." ;;
    esac
}

# ── Telegram bot token ─────────────────────────────────────────────────
validate_telegram_token() {
    local token="$1" body
    TELEGRAM_BOT_USERNAME=""
    if [[ ! "$token" =~ ^[0-9]{6,}:[A-Za-z0-9_-]{30,}$ ]]; then
        say_err "Telegram: that does not look like a bot token. It looks like 123456789:AAE... — copy the whole line from @BotFather."
        return 1
    fi
    body="$(curl -s --max-time "$VALIDATE_TIMEOUT" "https://api.telegram.org/bot${token}/getMe" 2>/dev/null || true)"
    if [[ "$body" != *'"ok":true'* ]]; then
        if [[ -z "$body" ]]; then
            say_err "Telegram: could not reach api.telegram.org. Check the internet connection."
        else
            say_err "Telegram: the token was rejected. Send /mybots to @BotFather and copy the token again."
        fi
        return 1
    fi
    # Extract "username":"..." without jq (not installed by default on macOS).
    TELEGRAM_BOT_USERNAME="$(printf '%s' "$body" \
        | sed -n 's/.*"username":"\([^"]*\)".*/\1/p' | head -n 1)"
    return 0
}

# ── DeepSeek (the model key hermes setup asks for) ─────────────────────
validate_deepseek_key() {
    local key="$1" code
    code="$(_http_status -H "Authorization: Bearer ${key}" "https://api.deepseek.com/models")"
    if [[ "$code" == "200" ]]; then
        return 0
    fi
    _explain_status "DeepSeek" "$code"
    [[ "$code" == "402" ]] && say_dim "  DeepSeek has no free tier — add a few dollars of prepaid balance at platform.deepseek.com."
    return 1
}

# ── Exa (primary search) ───────────────────────────────────────────────
validate_exa_key() {
    local key="$1" code
    code="$(printf '%s' '{"query":"morning report installer connectivity check","numResults":1,"type":"fast"}' \
        | _http_status -X POST \
            -H "Content-Type: application/json" \
            -H "x-api-key: ${key}" \
            --data @- "https://api.exa.ai/search")"
    if [[ "$code" == "200" ]]; then
        return 0
    fi
    _explain_status "Exa" "$code"
    return 1
}

# ── Firecrawl (page fetch) ─────────────────────────────────────────────
validate_firecrawl_key() {
    local key="$1" code
    code="$(printf '%s' '{"url":"https://example.com","formats":["markdown"]}' \
        | _http_status -X POST \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${key}" \
            --data @- "https://api.firecrawl.dev/v1/scrape")"
    if [[ "$code" == "200" ]]; then
        return 0
    fi
    _explain_status "Firecrawl" "$code"
    return 1
}

# ── Brave (optional search fallback) ───────────────────────────────────
validate_brave_key() {
    local key="$1" code
    code="$(_http_status -H "Accept: application/json" -H "X-Subscription-Token: ${key}" \
        "https://api.search.brave.com/res/v1/web/search?q=test&count=1")"
    if [[ "$code" == "200" ]]; then
        return 0
    fi
    _explain_status "Brave Search" "$code"
    return 1
}

# ── Wizard loop ────────────────────────────────────────────────────────
# collect_key VAR_NAME "Label" "signup url" validator_fn [optional]
#
# Idempotent: a value already stored in ~/.hermes/.env is re-validated and kept
# without asking, so a re-run after Ctrl+C does not re-ask for stored keys.
# Passes the key to the validator as an argument; only a masked form is printed.
collect_key() {
    local var_name="$1" label="$2" signup_url="$3" validator="$4" optional="${5:-required}"
    local existing value

    existing="$(env_get "$var_name")"
    if [[ -n "$existing" ]]; then
        printf '  Checking the %s key already saved on this Mac ... ' "$label"
        if "$validator" "$existing"; then
            printf '%sworks%s (%s)\n' "$C_GREEN" "$C_RESET" "$(mask_secret "$existing")"
            printf -v "$var_name" '%s' "$existing"
            return 0
        fi
        say_warn "  The saved $label key no longer works — asking for a new one."
    fi

    say ""
    say "  ${C_BOLD}${label}${C_RESET}"
    say_dim "  Sign up / copy the key here: $signup_url"
    if [[ "$optional" == "optional" ]]; then
        say_dim "  Optional — press Enter to skip it."
    fi

    while true; do
        value="$(prompt_secret "  Paste the $label key")"
        if [[ -z "$value" ]]; then
            if [[ "$optional" == "optional" ]]; then
                say_dim "  Skipped."
                printf -v "$var_name" '%s' ""
                return 0
            fi
            say_err "  This key is required."
            continue
        fi
        printf '  Checking it ... '
        if "$validator" "$value"; then
            printf '%sworks%s (%s)\n' "$C_GREEN" "$C_RESET" "$(mask_secret "$value")"
            printf -v "$var_name" '%s' "$value"
            return 0
        fi
        say_dim "  Nothing was saved. Try pasting it again."
    done
}
