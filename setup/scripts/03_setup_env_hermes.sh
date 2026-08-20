#!/usr/bin/env bash
# Bước 03: API key cho Morning Report skill (Exa + Firecrawl + Brave) vào ~/.hermes/.env.
# Telegram bot token + DeepSeek model key đã được cấu hình ở bước 02 (hermes setup wizard).
#
# BƯỚC NÀY BỎ QUA ĐƯỢC. Từ bản này, người dùng tự lấy key qua chat: skill `guided-setup`
# dẫn từng bước trên Telegram, họ dán key vào chat, bot kiểm tra với nhà cung cấp rồi ghi
# vào chính file .env này. Chỉ nhập ở đây khi BẠN đã có sẵn key trong tay và muốn máy chạy
# được ngay từ phút đầu.
#
# File user-owned, không cần sudo. Idempotent: update nếu đã có, append nếu chưa.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$DIR/config.env"

ENV_FILE="$OC_HOME/.hermes/.env"

set_env() {  # idempotent: update nếu có, append nếu chưa
    local key="$1" value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
    fi
}

mkdir -p "$OC_HOME/.hermes"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "================================================================"
echo "  API key cho Morning Report (Exa / Firecrawl / Brave)"
echo "================================================================"
echo
echo "Có 2 cách, chọn 1:"
echo
echo "  A. BỎ QUA ở đây (khuyến nghị khi khách tự trả tiền key)."
echo "     Sau khi cài xong, khách mở Telegram nhắn 'Cài đặt giúp tôi' — bot dẫn từng"
echo "     bước tạo key, khách dán vào chat, bot tự kiểm tra và ghi vào ~/.hermes/.env."
echo
echo "  B. Nhập ngay bây giờ (khi bạn đã có sẵn key)."
echo
echo "Cả 2 cách đều ghi vào cùng một file, làm sau vẫn được, không phải chạy lại bước nào."
echo
read -r -p "Bỏ qua và để người dùng tự làm qua chat? (Y để bỏ qua / n để nhập ngay): " SKIP
if [[ "${SKIP,,}" != "n" ]]; then
    echo
    echo "ĐÃ BỎ QUA bước 03. Nhắc khách câu đầu tiên khi bàn giao:"
    echo '  "Cài đặt giúp tôi"'
    echo
    echo "Muốn nhập bằng tay sau này: bash setup/scripts/03_setup_env_hermes.sh"
    exit 0
fi

echo
echo "Ghi search/fetch keys cho Morning Report skill vào $ENV_FILE"
echo "(Telegram + DeepSeek đã cấu hình ở bước 02. Bỏ trống ô nào thì để khách tự thêm"
echo " qua chat sau.)"
echo

read -r -p "Nhập EXA_API_KEY (search chính): " EXA_API_KEY
read -r -p "Nhập FIRECRAWL_API_KEY (fetch nội dung bài): " FIRECRAWL_API_KEY
read -r -p "Nhập BRAVE_SEARCH_API_KEY (search dự phòng): " BRAVE_SEARCH_API_KEY

# if, không phải `[[ ... ]] && ...`: dưới `set -e` một điều kiện sai ở vị trí cuối lệnh
# làm script thoát ngay, và bỏ trống ô key là chuyện bình thường ở bước này.
if [[ -n "$EXA_API_KEY" ]]; then set_env EXA_API_KEY "$EXA_API_KEY"; fi
if [[ -n "$FIRECRAWL_API_KEY" ]]; then set_env FIRECRAWL_API_KEY "$FIRECRAWL_API_KEY"; fi
if [[ -n "$BRAVE_SEARCH_API_KEY" ]]; then set_env BRAVE_SEARCH_API_KEY "$BRAVE_SEARCH_API_KEY"; fi

echo
echo "Đã ghi. Skill tự load ~/.hermes/.env mỗi lần chạy (không cần restart gateway cho skill)."
ls -l "$ENV_FILE"

if [[ -z "$EXA_API_KEY" && -z "$BRAVE_SEARCH_API_KEY" ]]; then
    echo
    echo "LƯU Ý: chưa có key tìm kiếm nào (Exa hoặc Brave) nên Morning Report chưa chạy được."
    echo "Khách bổ sung qua chat bằng câu: 'Cài đặt giúp tôi'."
fi
