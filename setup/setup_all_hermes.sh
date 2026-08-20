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
# 06: Google Workspace cho D2. Vẫn nằm trong luồng chính chứ không phải "tuỳ chọn sau khi
# cài" — thiếu nó thì doc-convert dựng file cục bộ, đúng loại file hiển thị lệch trên máy
# Mac, mà người cài không có cách nào biết. Bỏ qua được có chủ đích: khi Drive là tài
# khoản của khách, họ tự kết nối qua chat (skill guided-setup) mà không cần SSH tunnel.
run 06_google_oauth_hermes.sh

echo
echo "================================================================"
echo "HOÀN TẤT phần máy chủ. Phần còn lại làm TRONG CHAT — mở Telegram,"
echo "nhắn bot đúng một câu:"
echo
echo "      Cài đặt giúp tôi"
echo
echo "Bot sẽ tự kiểm tra còn thiếu gì, dẫn từng bước lấy key (Exa, Firecrawl,"
echo "Brave), kết nối Google, hỏi chủ đề + giờ gửi bản tin, rồi chạy thử một"
echo "lần để chứng minh là chạy được. Người dùng không cần đụng terminal."
echo
echo "Kiểm tra sức khoẻ (dành cho người quản trị): bash scripts/healthcheck_hermes.sh"
echo "================================================================"
