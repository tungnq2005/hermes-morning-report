#!/usr/bin/env bash
# Bước 06 (Hermes): kết nối Google Workspace cho doc-convert (D2) — ĐƯỜNG TERMINAL.
#
# CÓ ĐƯỜNG NGẮN HƠN: skill `guided-setup` làm đúng việc này ngay trong chat Telegram,
# không cần SSH tunnel — bot gửi link, người dùng bấm Cho phép rồi dán lại đường link
# trên thanh địa chỉ. Đó là đường mặc định cho khách tự kết nối tài khoản Google của họ.
# Script này vẫn giữ cho người cài có sẵn terminal và muốn làm xong luôn trong lúc deploy.
#
# Bước này nằm TRONG luồng setup chứ không phải tài liệu đọc thêm, vì hai lý do:
#   1. Không có Google thì D2 vẫn chạy nhưng dựng file bằng thư viện cục bộ — đúng loại
#      file hiển thị lệch trong PowerPoint trên máy Mac. Người cài dễ tưởng "chạy được
#      là xong" rồi bàn giao luôn.
#   2. Màn hình consent để ở chế độ Testing thì Google cho refresh token sống ĐÚNG 7
#      NGÀY. Bot chạy ngon cả tuần rồi chết với invalid_grant. Script này bắt người cài
#      xác nhận đã PUBLISH APP trước khi đi tiếp.
#
# Idempotent: đã có token hợp lệ thì chỉ kiểm tra lại rồi thoát.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # <repo>/setup
REPO_ROOT="$(cd "$DIR/.." && pwd)"                       # <repo>
# shellcheck disable=SC1091
source "$DIR/config.env"

ENV_FILE="$OC_HOME/.hermes/.env"
CREDS_DIR="${OC_GOOGLE_CREDS_DIR:-$OC_HOME/hermes-google-creds}"
SCOPES="${OC_GOOGLE_SCOPES:-minimal}"
PORT="${OC_GOOGLE_OAUTH_PORT:-8765}"
DOC_VI="docs/google-oauth-setup.vi.md"
AUTHORIZE="$REPO_ROOT/skills/doc-convert/scripts/authorize_google.py"
PREFLIGHT="$REPO_ROOT/skills/doc-convert/scripts/preflight.py"

set_env() {  # idempotent: update nếu có, append nếu chưa
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

preflight_google() {  # in ra JSON phần google
    DOC_CONVERT_GCREDS_DIR="$CREDS_DIR" DOC_CONVERT_GOOGLE_SCOPES="$SCOPES" \
        python3 "$PREFLIGHT" --compact 2>/dev/null \
        | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["checks"]["google"], ensure_ascii=False, indent=2))'
}

echo "================================================================"
echo "  Kết nối Google Workspace cho Document Conversion (D2)"
echo "================================================================"
echo
echo "Vì sao cần: bot dựng slide/tài liệu TRÊN Google rồi mới xuất file giao cho người"
echo "dùng. File .pptx do server tự dựng hiển thị lệch trên máy Mac; bản Google thì"
echo "giống nhau trên mọi máy. Bỏ qua bước này, D2 vẫn chạy nhưng kết quả kém hơn và"
echo "lệnh --to gslides / --to gdoc sẽ báo lỗi."
echo
echo "Bộ quyền sẽ xin: $SCOPES"
case "$SCOPES" in
    minimal)
        echo "  → chỉ drive.file: bot CHỈ đụng được file do chính nó tạo."
        echo "    Không đọc được link Google riêng tư người dùng dán vào."
        echo "    Đổi: đặt OC_GOOGLE_SCOPES=private-links trong config.env."
        ;;
    private-links)
        echo "  → drive.file + drive.readonly: đọc được link Google riêng tư."
        echo "    drive.readonly là scope RESTRICTED — người dùng sẽ thấy màn hình"
        echo "    'Google hasn't verified this app' và phải bấm Advanced → Continue."
        ;;
    *)
        echo "LỖI: OC_GOOGLE_SCOPES phải là 'minimal' hoặc 'private-links' (đang là '$SCOPES')." >&2
        exit 1
        ;;
esac
echo
echo "Bỏ qua ở đây là lựa chọn hợp lý khi Google Drive là TÀI KHOẢN CỦA KHÁCH: họ tự kết"
echo "nối qua chat, không phải đưa file client_secret.json cho bạn. Bảo khách nhắn bot:"
echo '  "Kết nối Google giúp tôi"'
echo
read -r -p "Bỏ qua Google và tiếp tục? (y để BỎ QUA, Enter để cài): " SKIP
if [[ "${SKIP,,}" == "y" ]]; then
    echo
    echo "ĐÃ BỎ QUA. Cho tới khi kết nối, D2 dựng file cục bộ và ghi cảnh báo"
    echo "'google_unauthorized:rendered_locally' trong manifest mỗi lần chuyển đổi."
    echo
    echo "Kết nối sau bằng 1 trong 2 đường:"
    echo "  • Qua chat (khách tự làm, không cần SSH): nhắn bot 'Kết nối Google giúp tôi'"
    echo "  • Qua terminal: bash setup/scripts/06_google_oauth_hermes.sh"
    exit 0
fi

# ── Đã có token chưa? ────────────────────────────────────────────────
if [[ -f "$CREDS_DIR/token.json" ]]; then
    echo
    echo "Đã có token tại $CREDS_DIR/token.json — kiểm tra lại:"
    preflight_google
    read -r -p "Cấp quyền lại từ đầu? (y/N): " REDO
    [[ "${REDO,,}" == "y" ]] || { echo "Giữ nguyên token hiện tại. Xong bước 06."; exit 0; }
fi

# ── Checklist Google Cloud Console ───────────────────────────────────
cat <<'EOF'

────────────────────────────────────────────────────────────────
LÀM TRÊN TRÌNH DUYỆT (console.cloud.google.com) — 5 phút
────────────────────────────────────────────────────────────────
Đăng nhập ĐÚNG tài khoản Google mà khách muốn file được tạo vào Drive của nó.

1. Chọn project → New Project → đặt tên (vd hermes-doc-convert) → Create.

2. APIs & Services → Library → bật:
     • Google Drive API    (BẮT BUỘC)
     • Google Slides API   (nên bật — để bot tự kiểm tra deck sau khi tạo)
   Không cần Google Docs API.

3. APIs & Services → OAuth consent screen → External → điền App name +
   2 email liên hệ → lưu qua hết các bước.

4. *** PUBLISHING STATUS → BẤM "PUBLISH APP" ***
   Để ở "Testing" thì Google cho refresh token sống ĐÚNG 7 NGÀY: bot chạy
   ngon cả tuần rồi chết với invalid_grant, không ai hiểu vì sao.
   Publish KHÔNG làm app hiện công khai — chỉ là trạng thái phát hành.

5. APIs & Services → Credentials → Create credentials → OAuth client ID
   → Application type: DESKTOP APP (không phải Web application)
   → Create → Download JSON.
────────────────────────────────────────────────────────────────

EOF
read -r -p "Đã PUBLISH APP ở mục 4 chưa? (gõ 'published' để xác nhận): " CONFIRM
if [[ "${CONFIRM,,}" != "published" ]]; then
    echo
    echo "Dừng ở đây. Publish app xong rồi chạy lại bước này —"
    echo "bỏ qua mục 4 nghĩa là bot sẽ chết sau đúng 7 ngày."
    exit 1
fi

# ── Nhận file client_secret.json ─────────────────────────────────────
mkdir -p "$CREDS_DIR"; chmod 700 "$CREDS_DIR"
if [[ ! -f "$CREDS_DIR/client_secret.json" ]]; then
    echo
    echo "Chép file JSON vừa tải lên VPS, ví dụ chạy Ở MÁY BẠN:"
    echo "  scp ~/Downloads/client_secret_*.json $OC_USER@<IP_VPS>:$CREDS_DIR/client_secret.json"
    echo
    read -r -p "Hoặc dán đường dẫn file JSON đã có sẵn trên VPS (Enter nếu đã scp xong): " SRC
    if [[ -n "$SRC" ]]; then
        [[ -f "$SRC" ]] || { echo "Không tìm thấy: $SRC" >&2; exit 1; }
        cp "$SRC" "$CREDS_DIR/client_secret.json"
    fi
fi
[[ -f "$CREDS_DIR/client_secret.json" ]] || {
    echo "LỖI: thiếu $CREDS_DIR/client_secret.json — chạy lại bước này sau khi chép file." >&2
    exit 1
}
chmod 600 "$CREDS_DIR/client_secret.json"

# Cảnh báo sớm nếu tạo nhầm loại client: Desktop client có khoá "installed".
python3 - "$CREDS_DIR/client_secret.json" <<'PY' || exit 1
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
kind = next(iter(data), "")
if kind != "installed":
    print(f"LỖI: đây là OAuth client loại '{kind}', cần loại Desktop app "
          "(file JSON có khoá 'installed'). Tạo lại client rồi tải JSON mới.", file=sys.stderr)
    raise SystemExit(1)
print("  client_secret.json hợp lệ (Desktop app).")
PY

# ── Ghi cấu hình vào ~/.hermes/.env ──────────────────────────────────
mkdir -p "$OC_HOME/.hermes"; touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
set_env DOC_CONVERT_GCREDS_DIR "$CREDS_DIR"
set_env DOC_CONVERT_GOOGLE_SCOPES "$SCOPES"
echo "  Đã ghi DOC_CONVERT_GCREDS_DIR + DOC_CONVERT_GOOGLE_SCOPES vào $ENV_FILE"

# ── Cấp quyền ────────────────────────────────────────────────────────
cat <<EOF

────────────────────────────────────────────────────────────────
VPS không có trình duyệt, nên mở SSH tunnel TỪ MÁY BẠN (cửa sổ khác):

  ssh -L $PORT:localhost:$PORT $OC_USER@<IP_VPS>

Giữ cửa sổ đó mở, rồi quay lại đây. Lệnh bên dưới sẽ in ra một URL —
dán vào trình duyệt máy bạn, chọn đúng tài khoản Google, bấm Cho phép.
────────────────────────────────────────────────────────────────

EOF
read -r -p "Đã mở tunnel chưa? Enter để bắt đầu cấp quyền... "

DOC_CONVERT_GCREDS_DIR="$CREDS_DIR" DOC_CONVERT_GOOGLE_SCOPES="$SCOPES" \
    python3 -u "$AUTHORIZE" --port "$PORT"

# ── Kiểm tra ─────────────────────────────────────────────────────────
echo
echo "Kiểm tra lại bằng preflight:"
preflight_google
echo
if DOC_CONVERT_GCREDS_DIR="$CREDS_DIR" python3 -c "
import json, subprocess, sys
out = subprocess.run([sys.executable, '$PREFLIGHT', '--compact'], capture_output=True, text=True).stdout
sys.exit(0 if json.loads(out)['checks']['google']['authorized_token'] else 1)
"; then
    echo "OK: Google đã sẵn sàng. D2 sẽ dựng kết quả trên Google Slides/Docs."
    echo
    read -r -p "Chạy thử một lần chuyển đổi thật? (Y/n): " TRY
    if [[ "${TRY,,}" != "n" ]]; then
        DOC_CONVERT_GCREDS_DIR="$CREDS_DIR" DOC_CONVERT_GOOGLE_SCOPES="$SCOPES" \
        python3 "$REPO_ROOT/skills/doc-convert/scripts/convert.py" \
            --input "$REPO_ROOT/docs/user-guide.vi.md" --to gslides --no-auto-images \
            --outdir /tmp/doc-convert-oauth-check \
            | python3 -c '
import json, sys
m = json.load(sys.stdin)
print("  success      :", m.get("success"))
print("  render_engine:", m.get("render_engine"), "(phải là google)")
print("  google_url   :", m.get("google_url"))
print("  google_check :", (m.get("google_check") or {}).get("status"), "(pass là đạt; unchecked = CHƯA kiểm tra được, thường do quên bật Slides API)")
print("  output (PDF) :", m.get("output"))
if m.get("warnings"): print("  warnings     :", m["warnings"])
'
        echo
        echo "  Mở google_url ở trên để khách xác nhận file nằm đúng tài khoản Drive."
    fi
else
    echo "CHƯA XONG: không thấy token hợp lệ." >&2
    echo "Tra bảng sự cố theo đúng thông điệp lỗi: $DOC_VI (mục 10)." >&2
    exit 1
fi

echo
echo "XONG bước 06. Chi tiết, câu hỏi của khách về quyền riêng tư, và bảng sự cố:"
echo "  $DOC_VI"
