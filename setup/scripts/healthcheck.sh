#!/usr/bin/env bash
# WS4: kiểm tra sức khoẻ hệ thống (bằng chứng cho AC "ổn định 48h").
# Chạy tay, hoặc đặt cron OpenClaw gọi định kỳ để cảnh báo operator.
# Exit 0 = khoẻ, exit 1 = có vấn đề. In JSON tóm tắt.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"
set -a; source /etc/openclaw/openclaw.env 2>/dev/null; set +a

WORKSPACE="$OC_HOME/.openclaw/workspace"
problems=()

# 1. Gateway service đang chạy?
active="$(systemctl --user is-active openclaw-gateway.service 2>/dev/null || echo inactive)"
[[ "$active" == "active" ]] || problems+=("gateway_not_active:$active")

# 2. Connectivity probe ok?
probe="$(openclaw gateway status 2>/dev/null | grep -c 'Connectivity probe: ok' || true)"
[[ "$probe" -ge 1 ]] || problems+=("probe_failed")

# 3. Secrets audit sạch?
audit="$(openclaw secrets audit --check 2>/dev/null | grep -c 'audit: clean' || true)"
[[ "$audit" -ge 1 ]] || problems+=("secrets_not_clean")

# 4. Có báo cáo morning-report trong 26h gần đây? (bằng chứng cron gửi được)
HIST="$WORKSPACE/skills/morning-report/state/report-history"
recent="$(find "$HIST" -type f -name 'manifest.json' -mmin -1560 2>/dev/null | wc -l)"
[[ "$recent" -ge 1 ]] || problems+=("no_recent_report_26h")

# 5. Đủ dung lượng đĩa (>1GB trống)?
free_kb="$(df -Pk "$OC_HOME" | awk 'NR==2{print $4}')"
[[ "${free_kb:-0}" -gt 1048576 ]] || problems+=("low_disk")

ok=true; problems_json=""
if [[ ${#problems[@]} -gt 0 ]]; then
  ok=false
  problems_json="$(printf '"%s",' "${problems[@]}" | sed 's/,$//')"
fi
printf '{"ok":%s,"gateway":"%s","recent_reports_26h":%s,"problems":[%s]}\n' \
  "$ok" "$active" "$recent" "$problems_json"

$ok && exit 0 || exit 1
