#!/usr/bin/env bash
# VPS bước 1: cập nhật Ubuntu, cài gói nền (D1 + D2) + xz-utils (cho Hermes install.sh),
# bật lingering cho user service.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

echo "[1/4] Cập nhật Ubuntu..."
sudo apt update
sudo apt upgrade -y

echo "[2/4] Cài gói nền D1 (bot, audio, cron) + xz-utils cho Hermes installer..."
sudo apt install -y curl wget git ca-certificates xz-utils openssl nano python3 jq ffmpeg rsync

echo "[3/4] Cài gói nền D2 (chuyển đổi tài liệu)..."
# LibreOffice headless để convert docx/pptx -> pdf; fonts để render tiếng Việt.
sudo apt install -y --no-install-recommends libreoffice-writer libreoffice-impress fonts-dejavu python3-pip
# Thư viện Python cho doc-convert. --break-system-packages vì Ubuntu 24.04+ khoá site-packages.
pip3 install --break-system-packages python-docx python-pptx pypdf \
  google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2

echo "[4/4] Bật lingering cho user $OC_USER..."
sudo loginctl enable-linger "$OC_USER"

LINGER="$(loginctl show-user "$OC_USER" -p Linger)"
echo "Kết quả: $LINGER"
if [[ "$LINGER" == "Linger=yes" ]]; then
  echo "OK: Lingering đã bật (gateway tự sống lại sau reboot VPS)."
else
  echo "LỖI: Lingering chưa bật (cần Linger=yes)." >&2
  exit 1
fi
