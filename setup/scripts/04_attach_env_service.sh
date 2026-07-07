#!/usr/bin/env bash
# Bước 7: gắn file env vào OpenClaw Gateway service.
# Thay cho lệnh tương tác `systemctl --user edit`, script ghi thẳng drop-in override.
set -euo pipefail

OVERRIDE_DIR="$HOME/.config/systemd/user/openclaw-gateway.service.d"
mkdir -p "$OVERRIDE_DIR"

cat > "$OVERRIDE_DIR/override.conf" <<'EOF'
[Service]
EnvironmentFile=/etc/openclaw/openclaw.env
EOF

echo "Đã ghi $OVERRIDE_DIR/override.conf"

systemctl --user daemon-reload
systemctl --user restart openclaw-gateway.service

echo
systemctl --user status openclaw-gateway.service --no-pager -l

echo
echo "Mục tiêu: Active: active (running)."
