#!/usr/bin/env bash
# Bước 5-6: tạo /etc/openclaw/openclaw.env chứa token/API key và khóa quyền file.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

ENV_FILE=/etc/openclaw/openclaw.env

if sudo test -f "$ENV_FILE"; then
  echo "CẢNH BÁO: $ENV_FILE đã tồn tại."
  read -r -p "Ghi đè? (y/N): " CONFIRM
  if [[ "${CONFIRM,,}" != "y" ]]; then
    echo "Bỏ qua, giữ nguyên file cũ."
    exit 0
  fi
  sudo cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
  echo "Đã backup file cũ."
fi

read -r -p "Nhập TELEGRAM_BOT_TOKEN (từ @BotFather): " TELEGRAM_BOT_TOKEN
read -r -p "Nhập MODEL_API_KEY (API key của model, vd DeepSeek): " MODEL_API_KEY

if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$MODEL_API_KEY" ]]; then
  echo "LỖI: token/key không được để trống." >&2
  exit 1
fi

# Key cho search provider (tùy chọn - chỉ hỏi nếu provider cần key).
SEARCH_KEY_LINE=""
case "$OC_SEARCH_PROVIDER" in
  tavily)
    read -r -p "Nhập TAVILY_API_KEY (search provider tavily): " TAVILY_API_KEY
    [[ -n "$TAVILY_API_KEY" ]] && SEARCH_KEY_LINE="TAVILY_API_KEY=$TAVILY_API_KEY" ;;
  google)
    read -r -p "Nhập GEMINI_API_KEY (Google search): " GEMINI_API_KEY
    [[ -n "$GEMINI_API_KEY" ]] && SEARCH_KEY_LINE="GEMINI_API_KEY=$GEMINI_API_KEY" ;;
  *) echo "Search provider = $OC_SEARCH_PROVIDER (không cần key riêng)." ;;
esac

OPENCLAW_GATEWAY_AUTH_TOKEN="$(openssl rand -hex 32)"
echo "Đã tự sinh OPENCLAW_GATEWAY_AUTH_TOKEN (64 ký tự hex)."

sudo mkdir -p /etc/openclaw
sudo tee "$ENV_FILE" >/dev/null <<EOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
OPENCLAW_GATEWAY_AUTH_TOKEN=$OPENCLAW_GATEWAY_AUTH_TOKEN
MODEL_API_KEY=$MODEL_API_KEY
${SEARCH_KEY_LINE}
EOF

echo "Khóa quyền file..."
sudo chown "$OC_USER:$OC_USER" "$ENV_FILE"
sudo chmod 600 "$ENV_FILE"

ls -l "$ENV_FILE"
echo "OK: đã tạo $ENV_FILE (quyền 600, owner $OC_USER:$OC_USER)."
