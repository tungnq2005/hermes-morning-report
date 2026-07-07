#!/usr/bin/env bash
# Bước 8: migrate secret sang SecretRef để token/API key không nằm plaintext trong config.
# Non-interactive (thay cho wizard) - đúng cách đã cho audit sạch ở môi trường dev.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

echo "Load env vào phiên hiện tại..."
set -a
# shellcheck disable=SC1091
source /etc/openclaw/openclaw.env
set +a

# Danh sách biến env có mặt (đưa vào allowlist provider).
ALLOW=(TELEGRAM_BOT_TOKEN OPENCLAW_GATEWAY_AUTH_TOKEN MODEL_API_KEY)
[[ -n "${TAVILY_API_KEY:-}" ]] && ALLOW+=(TAVILY_API_KEY)
[[ -n "${GEMINI_API_KEY:-}" ]] && ALLOW+=(GEMINI_API_KEY)

echo "[1] Tạo secrets provider 'default' (source=env)..."
ALLOW_ARGS=()
for v in "${ALLOW[@]}"; do ALLOW_ARGS+=(--provider-allowlist "$v"); done
openclaw config set secrets.providers.default --provider-source env "${ALLOW_ARGS[@]}"

echo "[2] Map channels.telegram.botToken -> TELEGRAM_BOT_TOKEN..."
openclaw config set channels.telegram.botToken --ref-provider default --ref-source env --ref-id TELEGRAM_BOT_TOKEN

echo "[3] Map gateway.auth.token -> OPENCLAW_GATEWAY_AUTH_TOKEN..."
openclaw config set gateway.auth.token --ref-provider default --ref-source env --ref-id OPENCLAW_GATEWAY_AUTH_TOKEN

echo "[4] Migrate model API key sang env-marker (auth-profile + models.json)..."
# Phát hiện provider model đang cấu hình (vd deepseek).
PROVIDER="$(openclaw models auth list 2>/dev/null | grep -oE '^- [a-z0-9_-]+:' | head -1 | tr -d '- :')"
PROVIDER="${PROVIDER:-deepseek}"
echo "    provider = $PROVIDER"
# Paste template ref vào auth-profile: gateway sẽ resolve \${MODEL_API_KEY} lúc chạy.
printf '%s\n' '${MODEL_API_KEY}' | openclaw models auth paste-api-key --provider "$PROVIDER" --profile-id "$PROVIDER:default" >/dev/null 2>&1 || true
# models.json: thay apiKey bằng marker tên biến env (được audit chấp nhận là non-secret).
MJ="$HOME/.openclaw/agents/main/agent/models.json"
if [[ -f "$MJ" ]]; then
  cp "$MJ" "$MJ.bak.$(date +%s)"
  jq --arg p "$PROVIDER" '.providers[$p].apiKey = "MODEL_API_KEY"' "$MJ" > "$MJ.tmp" && mv "$MJ.tmp" "$MJ"
fi

echo
echo "[5] Kiểm tra audit..."
openclaw secrets audit --check
echo "Mục tiêu: Secrets audit: clean. plaintext=0, unresolved=0, shadowed=0, legacy=0."

echo
echo "[6] Restart Gateway..."
systemctl --user restart openclaw-gateway.service
sleep 3
systemctl --user is-active openclaw-gateway.service

echo
echo "Nếu audit CHƯA sạch, xem Operator Runbook mục 'Secrets' để xử lý thủ công."
