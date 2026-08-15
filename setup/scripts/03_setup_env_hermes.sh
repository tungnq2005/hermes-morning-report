#!/usr/bin/env bash
# Bước 5-6: ghi API key cho Morning Report skill (Exa + Firecrawl + Brave) vào ~/.hermes/.env.
# Telegram bot token + DeepSeek model key đã được cấu hình ở bước 02 (hermes setup wizard).
# File user-owned, không cần sudo. Idempotent: update nếu đã có, append nếu chưa.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

ENV_FILE="$OC_HOME/.hermes/.env"

set_env() {  # idempotent: update nếu có, append nếu chưa
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

mkdir -p "$OC_HOME/.hermes"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "Ghi search/fetch keys cho Morning Report skill vào $ENV_FILE"
echo "(Telegram + DeepSeek đã cấu hình ở bước 02.)"
echo

read -r -p "Nhập EXA_API_KEY (search chính): " EXA_API_KEY
read -r -p "Nhập FIRECRAWL_API_KEY (fetch): " FIRECRAWL_API_KEY
read -r -p "Nhập BRAVE_SEARCH_API_KEY (fallback, có thể bỏ trống): " BRAVE_SEARCH_API_KEY

if [[ -z "$EXA_API_KEY" || -z "$FIRECRAWL_API_KEY" ]]; then
    echo "LỖI: EXA/FIRECRAWL không được trống." >&2
    exit 1
fi

set_env EXA_API_KEY "$EXA_API_KEY"
set_env FIRECRAWL_API_KEY "$FIRECRAWL_API_KEY"
[[ -n "$BRAVE_SEARCH_API_KEY" ]] && set_env BRAVE_SEARCH_API_KEY "$BRAVE_SEARCH_API_KEY"

echo
echo "Đã ghi. Skill tự load ~/.hermes/.env mỗi lần chạy (không cần restart gateway cho skill)."
ls -l "$ENV_FILE"
