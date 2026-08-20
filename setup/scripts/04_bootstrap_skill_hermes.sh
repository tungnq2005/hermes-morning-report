#!/usr/bin/env bash
# Bước 04 (Hermes): symlink CẢ BA skill (guided-setup + morning-report D1 + doc-convert D2)
# từ repo vào ~/.hermes/skills/ + chạy unit test + readiness. Nguồn skill là CHÍNH REPO NÀY
# (symlink để edit repo = update skill live).
#
# guided-setup phải có mặt TRƯỚC khi bàn giao: đây là skill dẫn người dùng tự lấy key và
# kết nối Google ngay trong chat. Thiếu nó thì mọi thứ còn thiếu key đều phải quay lại
# terminal — đúng thứ người dùng cuối không làm được.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # <repo>/setup
REPO_ROOT="$(cd "$DIR/.." && pwd)"                       # <repo>
# shellcheck disable=SC1091
source "$DIR/config.env"

HERMES_SKILLS="$OC_HOME/.hermes/skills"

echo "[1] Nguồn skill: $REPO_ROOT/skills"
for s in guided-setup morning-report doc-convert; do
  [[ -d "$REPO_ROOT/skills/$s" ]] || { echo "THIẾU skills/$s trong repo"; exit 1; }
done

echo "[2] Symlink skills vào ~/.hermes/skills/..."
mkdir -p "$HERMES_SKILLS/productivity" "$OC_HOME/.hermes"
ln -sfn "$REPO_ROOT/skills/guided-setup" "$HERMES_SKILLS/guided-setup"
ln -sfn "$REPO_ROOT/skills/morning-report" "$HERMES_SKILLS/productivity/morning-report"
ln -sfn "$REPO_ROOT/skills/doc-convert" "$HERMES_SKILLS/doc-convert"
ls -la "$HERMES_SKILLS/guided-setup" "$HERMES_SKILLS/productivity/morning-report" "$HERMES_SKILLS/doc-convert"

echo
echo "[3] Deploy SOUL.md (chỉ nếu chưa có, không đè bản live)..."
if [[ -f "$OC_HOME/.hermes/SOUL.md" ]]; then
  echo "  ~/.hermes/SOUL.md đã tồn tại — giữ nguyên."
else
  cp "$REPO_ROOT/SOUL.md" "$OC_HOME/.hermes/SOUL.md"
  echo "  Đã copy repo SOUL.md -> ~/.hermes/SOUL.md"
fi

echo
echo "[4] Unit test guided-setup..."
for t in "$REPO_ROOT"/skills/guided-setup/tests/test_*.py; do python3 "$t"; done

echo
echo "[4b] Diễn tập toàn bộ luồng cài đặt qua chat (offline, không đụng bản cài đang chạy)..."
# Chạy đúng các CLI mà bot sẽ chạy, trên HERMES_HOME tạm + Google giả. Bước này bắt được
# lỗi "cài xong mới biết luồng gãy" TRƯỚC khi khách ngồi vào máy.
python3 "$REPO_ROOT/skills/guided-setup/scripts/selftest.py"

echo
echo "[5] Unit test morning-report (D1)..."
for t in "$REPO_ROOT"/skills/morning-report/tests/test_*.py; do python3 "$t"; done

echo
echo "[6] Unit test doc-convert (D2)..."
for t in "$REPO_ROOT"/skills/doc-convert/tests/test_*.py; do python3 "$t"; done

echo
echo "[7] Readiness: những gì còn thiếu để bàn giao..."
python3 "$REPO_ROOT/skills/guided-setup/scripts/check_setup.py" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("  Morning Report chạy được :", d["ready"]["morning_report"])
print("  Google (doc-convert)     :", d["ready"]["doc_convert_google"])
print("  Còn thiếu                :", ", ".join(d["missing"]) or "không")
' || true

echo
echo "[8] Readiness D1 (config bản tin)..."
python3 "$REPO_ROOT/skills/morning-report/scripts/prepare_config.py" || true

echo
echo "[9] Preflight D2..."
python3 "$REPO_ROOT/skills/doc-convert/scripts/preflight.py" --compact

echo
echo "XONG bootstrap."
echo "Còn thiếu key hoặc Google? Không cần quay lại terminal: mở Telegram và nhắn bot"
echo '  "Cài đặt giúp tôi"  — bot sẽ dẫn từng bước lấy key và dán vào chat.'
