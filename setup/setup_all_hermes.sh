#!/usr/bin/env bash
# Chạy toàn bộ các bước setup Morning Brief (D1 + D2) trên VPS Ubuntu — Hermes Agent (NATIVE).
# Sửa config.env trước khi chạy. Mỗi bước sẽ prompt Enter để bạn kiểm soát.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$DIR/config.env" ]]; then
  echo "LỖI: thiếu $DIR/config.env." >&2
  echo "  cp config.env.example config.env  rồi sửa các giá trị cho đúng VPS." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$DIR/config.env"

echo "Cấu hình hiện tại (sửa trong config.env nếu cần):"
echo "  OC_USER=$OC_USER   OC_HOME=$OC_HOME"
echo "  TZ=$OC_TIMEZONE   Giờ gửi=$OC_DELIVERY_TIME"
echo

run() {
  echo
  echo "================================================================"
  echo ">>> BƯỨC: $1"
  echo "================================================================"
  read -r -p "Nhấn Enter để chạy (Ctrl+C để dừng)... "
  bash "$DIR/scripts/$1"
}

run 01_system_prep_hermes.sh
run 02_install_hermes.sh
run 03_setup_env_hermes.sh
run 04_bootstrap_skill_hermes.sh
# 05_searxng_hermes.sh: chỉ chạy nếu OC_SEARCH_PROVIDER=searxng
if [[ "${OC_SEARCH_PROVIDER:-}" == "searxng" ]]; then
  run 05_searxng_hermes.sh
fi

echo
echo "================================================================"
echo "HOÀN TẤT! Mở Telegram chat với bot để setup Morning Report:"
echo "  'Setup Morning Report cho tôi bằng skill morning report.'"
echo "  (hoặc chạy trực tiếp: python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --save --enable-cron)"
echo
echo "Kiểm tra sức khoẻ: bash scripts/healthcheck_hermes.sh"
echo "================================================================"
