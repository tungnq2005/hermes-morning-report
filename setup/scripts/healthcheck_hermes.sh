#!/usr/bin/env bash
# WS4 (Hermes): kiểm tra sức khoẻ hệ thống (bằng chứng cho AC "ổn định 48h").
# Chạy tay, hoặc đặt cron gọi định kỳ để cảnh báo operator.
# Exit 0 = khoẻ, exit 1 = có vấn đề. In JSON tóm tắt.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"
export PATH="$HOME/.local/bin:$PATH"

MR_HISTORY="$OC_HOME/.hermes/skills/productivity/morning-report/state/history"
problems=()

# 1. Gateway service đang chạy?
active="$(systemctl --user is-active hermes-gateway.service 2>/dev/null || echo inactive)"
[[ "$active" == "active" ]] || problems+=("gateway_not_active:$active")

# 2. hermes doctor sạch (deps/skills/memory/config)?
if hermes doctor >/dev/null 2>&1; then
  doctor_ok=true
else
  doctor_ok=false
  problems+=("doctor_not_clean")
fi

# 3. Có báo cáo morning-report trong 26h gần đây? (bằng chứng cron gửi được)
recent="$(find "$MR_HISTORY" -type f -name 'manifest.json' -mmin -1560 2>/dev/null | wc -l)"
[[ "$recent" -ge 1 ]] || problems+=("no_recent_report_26h")

# 4. Đủ dung lượng đĩa (>1GB trống)?
free_kb="$(df -Pk "$OC_HOME" | awk 'NR==2{print $4}')"
[[ "${free_kb:-0}" -gt 1048576 ]] || problems+=("low_disk")

# 5. Còn key nào thiếu/hỏng không? Key hết hạn mức là kiểu hỏng KHÔNG làm gateway chết,
# nên các mục trên vẫn xanh trong khi bản tin sáng thì trống. --verify gọi thật tới nhà
# cung cấp; mất mạng chỉ ra "unverified" nên không tạo báo động giả.
CHECK_SETUP="$(cd "$DIR/.." && pwd)/skills/guided-setup/scripts/check_setup.py"
keys_state="unknown"
if [[ -f "$CHECK_SETUP" ]]; then
  keys_state="$(python3 "$CHECK_SETUP" --verify 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unknown"); raise SystemExit
bad = [k["id"] for k in d["keys"] if k["status"] == "invalid"]
if bad:
    print("invalid:" + ",".join(bad))
elif not d["ready"]["morning_report"]:
    print("no_search_key")
else:
    print("ok")
' 2>/dev/null || echo unknown)"
  case "$keys_state" in
    ok|unknown) ;;
    *) problems+=("keys_$keys_state") ;;
  esac
fi

ok=true; problems_json=""
if [[ ${#problems[@]} -gt 0 ]]; then
  ok=false
  problems_json="$(printf '"%s",' "${problems[@]}" | sed 's/,$//')"
fi
printf '{"ok":%s,"gateway":"%s","doctor_ok":%s,"recent_reports_26h":%s,"keys":"%s","problems":[%s]}\n' \
  "$ok" "$active" "$doctor_ok" "$recent" "$keys_state" "$problems_json"

$ok && exit 0 || exit 1
