#!/usr/bin/env bash
# Bước 04 (Hermes): symlink CẢ HAI skill (morning-report D1 + doc-convert D2) từ repo
# vào ~/.hermes/skills/ + chạy unit test + readiness. Nguồn skill là CHÍNH REPO NÀY
# (symlink để edit repo = update skill live).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # <repo>/setup
REPO_ROOT="$(cd "$DIR/.." && pwd)"                       # <repo>
# shellcheck disable=SC1091
source "$DIR/config.env"

HERMES_SKILLS="$OC_HOME/.hermes/skills"

echo "[1] Nguồn skill: $REPO_ROOT/skills"
for s in morning-report doc-convert; do
  [[ -d "$REPO_ROOT/skills/$s" ]] || { echo "THIẾU skills/$s trong repo"; exit 1; }
done

echo "[2] Symlink skills vào ~/.hermes/skills/..."
mkdir -p "$HERMES_SKILLS/productivity" "$OC_HOME/.hermes"
ln -sfn "$REPO_ROOT/skills/morning-report" "$HERMES_SKILLS/productivity/morning-report"
ln -sfn "$REPO_ROOT/skills/doc-convert" "$HERMES_SKILLS/doc-convert"
ls -la "$HERMES_SKILLS/productivity/morning-report" "$HERMES_SKILLS/doc-convert"

echo
echo "[3] Deploy SOUL.md (chỉ nếu chưa có, không đè bản live)..."
if [[ -f "$OC_HOME/.hermes/SOUL.md" ]]; then
  echo "  ~/.hermes/SOUL.md đã tồn tại — giữ nguyên."
else
  cp "$REPO_ROOT/SOUL.md" "$OC_HOME/.hermes/SOUL.md"
  echo "  Đã copy repo SOUL.md -> ~/.hermes/SOUL.md"
fi

echo
echo "[4] Unit test morning-report (D1)..."
for t in "$REPO_ROOT"/skills/morning-report/tests/test_*.py; do python3 "$t"; done

echo
echo "[5] Unit test doc-convert (D2)..."
for t in "$REPO_ROOT"/skills/doc-convert/tests/test_*.py; do python3 "$t"; done

echo
echo "[6] Readiness D1 (config status)..."
python3 "$REPO_ROOT/skills/morning-report/scripts/prepare_config.py" || true

echo
echo "[7] Preflight D2..."
python3 "$REPO_ROOT/skills/doc-convert/scripts/preflight.py" --compact

echo
echo "XONG bootstrap. Setup Morning Report qua Telegram (hoặc prepare_config.py --save --enable-cron)."
