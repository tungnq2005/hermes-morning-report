#!/usr/bin/env bash
# Bước 12 (D3): cấu hình integration production - tool profile, search provider, command owner.
# Chạy SAU 06_bootstrap. Idempotent: chạy lại nhiều lần không sao.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
set -a; source /etc/openclaw/openclaw.env 2>/dev/null; set +a

echo "[1] Mở lại tool tts + message (profile 'coding' mặc định gỡ mất - bài học D1)..."
openclaw config set tools.alsoAllow '["group:messaging","tts"]' --strict-json

echo "[1b] Model: flash làm default + pro fallback (bài học: pro là reasoning model,"
echo "     compose dài dễ treo >9 phút -> watchdog hủy run -> 'LLM request failed')..."
openclaw models set deepseek/deepseek-v4-flash 2>&1 | tail -1 || true
openclaw models fallbacks add deepseek/deepseek-v4-pro 2>&1 | tail -1 || true

echo "[2] Cấu hình search provider = $OC_SEARCH_PROVIDER ..."
openclaw config set tools.web.search.enabled true --strict-json
openclaw config set tools.web.search.provider "$OC_SEARCH_PROVIDER"
case "$OC_SEARCH_PROVIDER" in
  tavily)  echo "    -> cần TAVILY_API_KEY trong env (đã thêm ở bước 03 nếu nhập)." ;;
  google)  echo "    -> cần GEMINI_API_KEY trong env." ;;
  searxng) echo "    -> nhớ chạy 08_searxng.sh để dựng instance SearXNG local." ;;
  brave)   echo "    -> CẢNH BÁO: Brave free tier bị 429 rate-limit. Cân nhắc đổi provider." ;;
esac

if [[ -n "${OC_OWNER_TELEGRAM_ID:-}" ]]; then
  echo "[3] Set command owner = telegram:$OC_OWNER_TELEGRAM_ID ..."
  openclaw config set commands.ownerAllowFrom "[\"telegram:$OC_OWNER_TELEGRAM_ID\"]" --strict-json
else
  echo "[3] Bỏ qua command owner (OC_OWNER_TELEGRAM_ID trống). Set sau bằng:"
  echo "    openclaw config set commands.ownerAllowFrom '[\"telegram:<id>\"]' --strict-json"
fi

echo "[4] Restart gateway để áp dụng..."
systemctl --user restart openclaw-gateway.service
sleep 3
systemctl --user is-active openclaw-gateway.service

echo
echo "GHI CHÚ về cron: sau khi setup Morning Report qua chat, đặt giờ gửi = $OC_DELIVERY_TIME"
echo "múi giờ $OC_TIMEZONE (production 7h sáng). Kiểm tra bằng: openclaw cron list"

echo
echo "=== Google Workspace (tùy chọn - đọc file Google riêng tư + tạo draft cloud) ==="
GCREDS="$OC_HOME/.openclaw/workspace/skills/doc-convert/state/google-creds"
if [[ -f "$GCREDS/token.json" ]]; then
  echo "  ĐÃ authorize (token.json tồn tại)."
elif [[ -f "$GCREDS/client_secret.json" ]]; then
  echo "  Có client_secret nhưng CHƯA authorize. Chạy 1 lần:"
  echo "    cd $OC_HOME/.openclaw/workspace && python3 skills/doc-convert/scripts/authorize_google.py --port 8765"
  echo "  (VPS headless: SSH tunnel 'ssh -L 8765:localhost:8765 $OC_USER@<vps>' rồi mở URL in ra.)"
else
  echo "  Chưa cấu hình Google. Nếu cần: đặt client_secret.json vào $GCREDS/ rồi chạy authorize_google.py."
  echo "  Nhớ enable Google Drive API + Docs API + Slides API trong Google Cloud Console."
fi
