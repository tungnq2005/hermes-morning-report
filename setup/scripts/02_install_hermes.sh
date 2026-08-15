#!/usr/bin/env bash
# Hermes bước 1-3: cài CLI (NATIVE, không Docker), onboarding, cài+start gateway service.
# Chạy bằng user thường (vd ubuntu). Phần sudo (loginctl) đã làm ở bước 01.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

echo "[1/4] Cài Hermes CLI (native, không sudo)..."
# Installer tạo ~/.hermes/hermes-agent/ và đặt hermes vào ~/.local/bin/.
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Nạp lại PATH phòng installer vừa thêm ~/.local/bin.
export PATH="$HOME/.local/bin:$PATH"
hash -r

echo "[2/4] Kiểm tra CLI..."
hermes --version

echo "[3/4] Onboarding (wizard TƯƠNG TÁC):"
cat <<EOF
  Wizard đầy đủ:  hermes setup
    - model:    chọn provider DeepSeek + dán API key
                (hoặc chạy "hermes setup --portal" nếu dùng Nous Portal)
    - gateway:  chọn Telegram + bot token + allowed users + home channel
  Hoặc chạy từng section:  "hermes setup model"  /  "hermes gateway setup"
  Linger đã bật ở bước 01; user service sẽ chạy bằng user hiện tại ($OC_USER).
EOF
hermes setup

echo "[4/4] Cài + enable + start gateway service (systemd user service)..."
# --start-now + --start-on-login: enable + start ngay, không cần "hermes gateway start" riêng.
hermes gateway install --start-now --start-on-login

echo
echo "--- Kiểm tra ---"
hermes gateway status --deep
hermes doctor || true
systemctl --user status hermes-gateway.service --no-pager -l

echo
echo "Mục tiêu: gateway active (running), doctor sạch, service enabled. Xong bước 02."
