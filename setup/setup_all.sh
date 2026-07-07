#!/usr/bin/env bash
# Chạy toàn bộ các bước setup Morning Brief (D1 + D2) trên VPS Ubuntu, cài NATIVE.
# Sửa config.env trước khi chạy.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

echo "Cấu hình hiện tại (sửa trong config.env nếu cần):"
echo "  OC_USER=$OC_USER   OC_HOME=$OC_HOME   OC_PORT=$OC_PORT"
echo "  Search=$OC_SEARCH_PROVIDER   TZ=$OC_TIMEZONE   Giờ gửi=$OC_DELIVERY_TIME"
echo

run() {
  echo
  echo "================================================================"
  echo ">>> BƯỚC: $1"
  echo "================================================================"
  read -r -p "Nhấn Enter để chạy (Ctrl+C để dừng)... "
  bash "$DIR/scripts/$1"
}

run 01_system_prep.sh
run 02_install_openclaw.sh
run 03_setup_env.sh
run 04_attach_env_service.sh
run 05_migrate_secrets.sh
run 06_bootstrap_skill.sh
run 07_configure_integrations.sh
# 08_searxng.sh: chỉ chạy nếu OC_SEARCH_PROVIDER=searxng
if [[ "$OC_SEARCH_PROVIDER" == "searxng" ]]; then
  run 08_searxng.sh
fi

echo
echo "================================================================"
echo "HOÀN TẤT! Mở Telegram và chat với bot:"
echo "  'Setup Morning Report cho tôi bằng skill morning report.'"
echo
echo "Kiểm tra sức khoẻ bất kỳ lúc nào: bash scripts/healthcheck.sh"
echo "================================================================"
