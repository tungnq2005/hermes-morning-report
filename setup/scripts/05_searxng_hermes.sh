#!/usr/bin/env bash
# Bước 05 (TÙY CHỌN - Hermes): dựng SearXNG local (Docker riêng) + trỏ Hermes web tool sang nó.
# Morning Report skill dùng Exa+Brave trực tiếp, KHÔNG cần SearXNG. Script này chỉ dành cho
# ai muốn SearXNG làm search provider cho platform `web` tool của Hermes (agent web search chung).
# SearXNG chạy Docker RIÊNG - không ảnh hưởng Hermes native (browser tool vẫn còn).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.local/bin:$PATH"

SEARX_PORT="${SEARX_PORT:-8888}"
SEARX_URL="http://127.0.0.1:${SEARX_PORT}"

echo "[1] Cài Docker nếu chưa có..."
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo bash
  sudo usermod -aG docker "$OC_USER" || true
fi

echo "[2] Chạy SearXNG container (JSON API bật sẵn)..."
sudo docker rm -f searxng 2>/dev/null || true
sudo mkdir -p /etc/searxng
if ! sudo grep -q 'formats:' /etc/searxng/settings.yml 2>/dev/null; then
  echo -e "search:\n  formats:\n    - html\n    - json" | sudo tee /etc/searxng/settings.yml >/dev/null
fi
sudo docker run -d --name searxng --restart always \
  -p "127.0.0.1:${SEARX_PORT}:8080" \
  -v /etc/searxng:/etc/searxng \
  searxng/searxng:latest

sleep 5
echo "[3] Kiểm tra SearXNG..."
curl -fsS "${SEARX_URL}/search?q=test&format=json" >/dev/null \
  && echo "OK: SearXNG trả JSON tại ${SEARX_URL}" \
  || { echo "LỖI: SearXNG chưa trả JSON. Xem: sudo docker logs searxng"; exit 1; }

echo
echo "[4] Trỏ Hermes web tool sang SearXNG (search backend)..."
ENV_FILE="$(hermes config env-path)"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
if grep -q '^SEARXNG_URL=' "$ENV_FILE"; then
  sed -i "s|^SEARXNG_URL=.*|SEARXNG_URL=${SEARX_URL}|" "$ENV_FILE"
else
  printf '\nSEARXNG_URL=%s\n' "$SEARX_URL" >> "$ENV_FILE"
fi
echo "  Đã set SEARXNG_URL=${SEARX_URL} trong $ENV_FILE"
hermes config set web.search_backend searxng
echo "  Đã set web.search_backend=searxng (config.yaml)."
echo "  Lưu ý: SearXNG là search-only. web.extract_backend giữ nguyên;"
echo "  Morning Report skill dùng Exa+Firecrawl trực tiếp (không qua platform web tool)."

echo
echo "[5] Restart gateway để apply..."
hermes gateway restart
sleep 3
systemctl --user is-active --quiet hermes-gateway.service && echo "  OK: gateway active." \
  || { echo "  LỖI: gateway không active." >&2; exit 1; }

echo
echo "[6] Verify (optional):"
echo "  source ~/.hermes/hermes-agent/.venv/bin/activate && python -m tools.web_tools"
echo "  -> kỳ vọng 'Web backend: searxng'"
echo "XONG SearXNG (optional)."
