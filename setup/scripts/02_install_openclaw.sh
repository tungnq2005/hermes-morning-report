#!/usr/bin/env bash
# OpenClaw bước 1-4: cài CLI (NATIVE, không Docker), onboarding + daemon, kiểm tra gateway.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

echo "[1/3] Cài OpenClaw..."
curl -fsSL https://openclaw.ai/install.sh | bash

# Nạp lại PATH phòng khi installer vừa thêm đường dẫn mới
export PATH="$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
hash -r

echo "[2/3] Kiểm tra CLI..."
openclaw --version

echo "[3/3] Chạy onboarding (wizard TƯƠNG TÁC - trả lời theo bảng dưới):"
cat <<'EOF'
  Daemon:  Yes
  Runtime: Node
  Service: systemd user service   <-- NATIVE, KHÔNG chọn Docker (giữ tool browser)
  Bind:    127.0.0.1 / loopback
  Port:    $OC_PORT
  Run as:  $OC_USER
EOF
openclaw onboard --install-daemon

echo
echo "--- Kiểm tra sau onboarding ---"
openclaw gateway status
openclaw doctor
systemctl --user status openclaw-gateway.service --no-pager -l

echo
echo "Mục tiêu: gateway running / doctor complete / service active (running)."
