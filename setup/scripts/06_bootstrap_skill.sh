#!/usr/bin/env bash
# Bước 06: cài CẢ HAI skill (morning-report D1 + doc-convert D2) vào workspace + test.
#
# Nguồn skill là CHÍNH REPO NÀY. Trước đây script clone một repo upstream khác và
# rsync hai thư mục skills-local/ + overlays/ không còn tồn tại, nên client chạy
# setup_all.sh sẽ nhận D1 cũ và không có D2.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # <repo>/setup
REPO_ROOT="$(cd "$DIR/.." && pwd)"                       # <repo>
# shellcheck disable=SC1091
source "$DIR/config.env"

WORKSPACE="$OC_HOME/.openclaw/workspace"

echo "[1] Nguồn skill: $REPO_ROOT/skills"
for s in morning-report doc-convert; do
  [[ -d "$REPO_ROOT/skills/$s" ]] || { echo "THIẾU skills/$s trong repo"; exit 1; }
done

echo "[2] Copy skills + AGENTS.md vào workspace..."
mkdir -p "$WORKSPACE/skills"
# state/ là runtime của từng máy (token Google, lịch sử run) — không bao giờ đè.
rsync -a --exclude 'state/' --exclude '__pycache__/' \
  "$REPO_ROOT/skills/" "$WORKSPACE/skills/"
rsync -a "$REPO_ROOT/AGENTS.md" "$WORKSPACE/AGENTS.md"

cd "$WORKSPACE"

echo
echo "[3] Unit test morning-report (D1)..."
python3 -m unittest discover skills/morning-report/tests

echo
echo "[4] Unit test doc-convert (D2)..."
python3 -m unittest discover skills/doc-convert/tests

echo
echo "[5] Readiness D1..."
python3 skills/morning-report/scripts/setup/run.py --compact

echo
echo "[6] Preflight D2..."
python3 skills/doc-convert/scripts/preflight.py --compact

echo
echo "XONG bootstrap. Tiếp theo chạy 07_configure_integrations.sh rồi setup qua Telegram:"
echo "  'Setup Morning Report cho tôi bằng skill morning report.'"
