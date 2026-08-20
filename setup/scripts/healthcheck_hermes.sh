#!/usr/bin/env bash
# Health check for the Hermes morning-report system. Works on both supported
# hosts: an Ubuntu VPS (systemd user service) and an always-on macOS desktop
# (launchd LaunchAgent).
#
# Run by hand, by `hermes-check`, or every 15 minutes by the macOS watchdog.
# Exit 0 = healthy, exit 1 = a problem. Prints a one-line JSON summary.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# config.env only exists on the VPS install path; macOS deliberately has none
# (its `getent`-based OC_HOME probe does not work on macOS anyway).
if [[ -f "$DIR/config.env" ]]; then
    # shellcheck disable=SC1091
    source "$DIR/config.env"
fi
: "${OC_HOME:=$HOME}"
export PATH="$HOME/.local/bin:$PATH"

MR_HISTORY="$OC_HOME/.hermes/skills/productivity/morning-report/state/history"
INSTALLED_MARKER="$OC_HOME/.hermes/.installed-at"
GATEWAY_LABEL="ai.hermes.gateway"
OS_NAME="$(uname -s)"
problems=()
sleep_setting="n/a"

# ── 1. Is the gateway running? ─────────────────────────────────────────
gateway_process_count() {
    # Matches the LaunchAgent form (`python -m hermes_cli.main gateway run`) and a
    # stray foreground/nohup one (`hermes gateway`), while ignoring the watchdog
    # and short-lived `hermes gateway install|status` calls.
    pgrep -fl gateway 2>/dev/null \
        | grep -E "(hermes_cli\.main([[:space:]]+--profile[[:space:]]+[^[:space:]]+)?[[:space:]]+gateway|/hermes[[:space:]]+gateway|^[0-9]+[[:space:]]+hermes[[:space:]]+gateway)" \
        | grep -Ev "watchdog|gateway (install|status|stop|start|setup)" \
        | wc -l | tr -d ' '
}

if [[ "$OS_NAME" == "Darwin" ]]; then
    proc_count="$(gateway_process_count)"
    if [[ "$proc_count" == "1" ]]; then
        active="active"
    elif [[ "$proc_count" == "0" ]]; then
        active="inactive"
        problems+=("gateway_not_running")
    else
        # Telegram allows exactly one long-poller per bot token; two gateways mean
        # 409 Conflict with duplicated or dropped messages.
        active="duplicate:$proc_count"
        problems+=("multiple_gateway_processes:$proc_count")
    fi
    # Check both domains: gui/$UID is normal for a logged-in session, but Hermes
    # falls back to user/$UID (gateway.py `_launchd_domain()`). Testing only gui
    # would report a perfectly healthy agent as missing.
    if ! launchctl print "gui/$(id -u)/${GATEWAY_LABEL}" >/dev/null 2>&1 \
       && ! launchctl print "user/$(id -u)/${GATEWAY_LABEL}" >/dev/null 2>&1; then
        problems+=("launchagent_not_loaded")
    fi
    if [[ -f "$OC_HOME/.hermes/.gateway-launchd-unsupported" ]]; then
        # Hermes fell back to a detached process: alive now, gone after a restart.
        problems+=("launchd_unsupported_fallback")
    fi
else
    active="$(systemctl --user is-active hermes-gateway.service 2>/dev/null || echo inactive)"
    [[ "$active" == "active" ]] || problems+=("gateway_not_active:$active")
fi

# ── 2. Is `hermes doctor` clean? ───────────────────────────────────────
if hermes doctor >/dev/null 2>&1; then
    doctor_ok=true
else
    doctor_ok=false
    problems+=("doctor_not_clean")
fi

# ── 3. Has a report been produced in the last 26h? ─────────────────────
# Proof the whole cron -> skill -> Telegram path works. Suppressed for the first
# 26h after install: otherwise a fresh machine reports ok:false straight away and
# the customer calls support about a system that is fine.
recent="$(find "$MR_HISTORY" -type f -name 'manifest.json' -mmin -1560 2>/dev/null | wc -l | tr -d ' ')"
in_grace=false
if [[ "$recent" -lt 1 && -f "$INSTALLED_MARKER" ]]; then
    if [[ -n "$(find "$INSTALLED_MARKER" -mmin -1560 2>/dev/null)" ]]; then
        in_grace=true
    fi
fi
if [[ "$recent" -lt 1 && "$in_grace" != "true" ]]; then
    problems+=("no_recent_report_26h")
fi

# ── 4. Enough free disk (>1GB)? ────────────────────────────────────────
free_kb="$(df -Pk "$OC_HOME" | awk 'NR==2{print $4}')"
[[ "${free_kb:-0}" -gt 1048576 ]] || problems+=("low_disk")

# ── 5. macOS only: the Mac must not be allowed to sleep ────────────────
# A sleeping Mac suspends the gateway: no report, no error message anywhere.
# Read `pmset -g custom` (the stored setting), not `pmset -g`, which reports the
# effective value including transient assertions like caffeinate.
if [[ "$OS_NAME" == "Darwin" ]]; then
    sleep_setting="$(pmset -g custom 2>/dev/null \
        | grep -E '^[[:space:]]*sleep[[:space:]]+[0-9]+' \
        | head -n 1 | awk '{print $2}')"
    : "${sleep_setting:=unknown}"
    [[ "$sleep_setting" == "0" ]] || problems+=("machine_can_sleep:$sleep_setting")
fi

# 6. Còn key nào thiếu/hỏng không? Key hết hạn mức là kiểu hỏng KHÔNG làm gateway chết,
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
printf '{"ok":%s,"os":"%s","gateway":"%s","doctor_ok":%s,"recent_reports_26h":%s,"install_grace":%s,"sleep_setting":"%s","keys":"%s","problems":[%s]}\n' \
  "$ok" "$OS_NAME" "$active" "$doctor_ok" "$recent" "$in_grace" "$sleep_setting" "$keys_state" "$problems_json"

$ok && exit 0 || exit 1
