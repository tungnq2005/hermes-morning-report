#!/usr/bin/env bash
# Bước 13 (TÙY CHỌN - chỉ khi OC_SEARCH_PROVIDER=searxng): dựng SearXNG local, miễn phí.
# SearXNG chạy trong Docker RIÊNG - KHÔNG ảnh hưởng OpenClaw native (browser tool vẫn còn).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

SEARX_PORT="${SEARX_PORT:-8888}"

echo "[1] Cài Docker nếu chưa có..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo bash
  sudo usermod -aG docker "$OC_USER" || true
fi

echo "[2] Chạy SearXNG container (JSON API bật sẵn)..."
sudo docker rm -f searxng 2>/dev/null || true
sudo mkdir -p /etc/searxng
# Bật format json để OpenClaw gọi API được.
if ! sudo grep -q 'formats:' /etc/searxng/settings.yml 2>/dev/null; then
  echo -e "search:\n  formats:\n    - html\n    - json" | sudo tee /etc/searxng/settings.yml >/dev/null
fi
sudo docker run -d --name searxng --restart always \
  -p "127.0.0.1:${SEARX_PORT}:8080" \
  -v /etc/searxng:/etc/searxng \
  searxng/searxng:latest

sleep 5
echo "[3] Kiểm tra SearXNG..."
curl -fsS "http://127.0.0.1:${SEARX_PORT}/search?q=test&format=json" >/dev/null \
  && echo "OK: SearXNG trả JSON tại 127.0.0.1:${SEARX_PORT}" \
  || { echo "LỖI: SearXNG chưa trả JSON. Xem: sudo docker logs searxng"; exit 1; }

echo "[4] Trỏ OpenClaw sang SearXNG..."
openclaw config set tools.web.search.provider searxng
openclaw config set tools.web.search.searxng.baseUrl "http://127.0.0.1:${SEARX_PORT}" 2>/dev/null || \
  echo "    (nếu key config khác, chỉnh theo openclaw config get tools.web.search)"
systemctl --user restart openclaw-gateway.service
echo "XONG SearXNG."
