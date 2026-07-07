#!/usr/bin/env bash
# Bước 11: bootstrap CẢ HAI skill (morning-report D1 + doc-convert D2) vào workspace + test.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

REPO_DIR="$OC_HOME/openclaw-workspace-repo"
WORKSPACE="$OC_HOME/.openclaw/workspace"

cd "$OC_HOME"

echo "[1] Lấy skill morning-report (D1) từ repo upstream..."
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull
else
  git clone "$OC_REPO_URL" "$REPO_DIR"
fi

mkdir -p "$WORKSPACE/skills"
echo "[2] Copy skills + AGENTS.md từ repo..."
rsync -a "$REPO_DIR/skills/" "$WORKSPACE/skills/"
rsync -a "$REPO_DIR/AGENTS.md" "$WORKSPACE/AGENTS.md"

echo "[3] Copy skill doc-convert (D2, đóng gói local)..."
rsync -a "$DIR/skills-local/" "$WORKSPACE/skills/"

echo "[4] Áp bản vá overlay (fix media-path trong audio-runtime.md)..."
if [[ -d "$DIR/overlays" ]]; then
  rsync -a "$DIR/overlays/" "$WORKSPACE/skills/"
fi

cd "$WORKSPACE"
echo
echo "[5] Unit test morning-report (D1)..."
python3 -m unittest discover skills/morning-report/tests
echo
echo "[6] Unit test doc-convert (D2)..."
python3 -m unittest discover skills/doc-convert/tests

echo
echo "[7] Preflight D1..."
python3 skills/morning-report/scripts/preflight.py --compact
echo
echo "[8] Preflight D2..."
python3 skills/doc-convert/scripts/preflight.py --compact

echo
echo "XONG bootstrap. Tiếp theo chạy 07_configure_integrations.sh rồi setup qua Telegram:"
echo "  'Setup Morning Report cho tôi bằng skill morning report.'"
