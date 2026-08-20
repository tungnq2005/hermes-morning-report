# Morning Brief Setup — Hermes Agent (D1 + D2 + D3)

Bộ script + tài liệu để deploy trợ lý AI Telegram (Hermes Agent, cài **NATIVE** không Docker) lên VPS Ubuntu, gồm cả 3 skill và tài liệu bàn giao.

- **D1 — Morning Report**: bot gửi bản tin sáng (text + audio 3–5 phút) qua cron, per-topic.
- **D2 — Document Conversion**: chuyển đổi Word/PPT/PDF/Markdown + tường thuật audio — nhận cả file người dùng gửi lẫn **bản tin do D1 tạo ra** (nhắn "Xuất bản tin sáng nay ra Google Docs").
- **D3 — Technical Setup**: provisioning, integration, giám sát, tài liệu, bàn giao.

## Cài đặt chia làm 2 nửa

| | Ai làm | Ở đâu | Gồm những gì |
| --- | --- | --- | --- |
| **Nửa máy chủ** | người cài (bạn) | terminal của VPS | OS, Hermes gateway, Telegram bot token, model key, cài 3 skill |
| **Nửa cấu hình** | **người dùng cuối** | **chat Telegram** | API key tìm tin, kết nối Google, chủ đề + giờ gửi bản tin |

Nửa thứ hai do skill **`guided-setup`** đảm nhiệm: người dùng nhắn *"Cài đặt giúp tôi"*, bot
kiểm tra còn thiếu gì, dẫn từng bước tạo key trên trình duyệt của họ, nhận key họ **dán vào
chat**, tự kiểm tra với nhà cung cấp rồi ghi vào `~/.hermes/.env` (quyền 600). Kết nối Google
cũng làm trong chat — **không cần SSH tunnel**: bot gửi link, người dùng bấm Cho phép, rồi dán
lại đường link trên thanh địa chỉ.

Nghĩa là bạn **không cần cầm key của khách**. Đây cũng là cách đúng khi Google Drive là tài
khoản của khách: họ tự cấp quyền, bạn không đụng vào `client_secret.json` của họ.

## Cấu trúc

```
hermes-morning-report/
├── config.env                 <- SỬA TRƯỚC: user, timezone, giờ gửi, search provider
├── setup_all_hermes.sh        <- chạy tất cả các bước theo thứ tự
├── scripts/
│   ├── 01_system_prep_hermes.sh        cập nhật OS + gói nền D1 & D2 + xz-utils + lingering
│   ├── 02_install_hermes.sh            cài Hermes CLI + hermes setup (wizard) + gateway service (NATIVE)
│   ├── 03_setup_env_hermes.sh          (bỏ qua được) nhập sẵn EXA/Firecrawl/Brave thay cho khách
│   ├── 04_bootstrap_skill_hermes.sh    symlink CẢ 3 skill từ ../skills/ + test + readiness
│   ├── 05_searxng_hermes.sh            (tùy chọn) SearXNG cho platform web tool (skill không cần)
│   ├── 06_google_oauth_hermes.sh       (bỏ qua được) kết nối Google bằng terminal + SSH tunnel
│   └── healthcheck_hermes.sh           kiểm tra sức khoẻ (bằng chứng ổn định 48h)
└── docs/
    ├── user-guide.vi.md / .en.md      hướng dẫn người dùng cuối (song ngữ)
    ├── operator-runbook.vi.md / .en.md  sổ tay vận hành cho quản trị (song ngữ)
    ├── chat-commands.md               bảng lệnh nhanh 1 trang (song ngữ)
    └── handover-session.md            kịch bản bàn giao 30 phút + checklist nghiệm thu
```

## Cách deploy lên VPS

```bash
# SSH vào VPS Ubuntu rồi clone repo — bước 04 symlink skill từ chính bản clone.
git clone https://github.com/tungnq2005/hermes-morning-report.git
cd hermes-morning-report/setup
chmod +x setup_all_hermes.sh scripts/*.sh

cp config.env.example config.env   # setup_all_hermes.sh source config.env, không phải .example
nano config.env                    # sửa OC_USER, OC_TIMEZONE, OC_DELIVERY_TIME, OC_SEARCH_PROVIDER

./setup_all_hermes.sh         # chạy tuần tự, dừng xác nhận trước mỗi bước
```

Các bước script sẽ chạy:

| Bước | Làm gì | Cần bạn thao tác gì |
| --- | --- | --- |
| 01 | Cài gói hệ thống (LibreOffice, python libs, font Carlito) | không |
| 02 | `hermes setup` + cài gateway systemd | wizard: chọn model DeepSeek, dán Telegram bot token |
| 03 | *(bỏ qua được)* Ghi sẵn `EXA_API_KEY` / `FIRECRAWL_API_KEY` / `BRAVE_SEARCH_API_KEY` | chỉ khi bạn đã cầm sẵn key; mặc định Enter để khách tự làm qua chat |
| 04 | Symlink 3 skill từ repo + chạy unit test + preflight | không |
| 05 | SearXNG (chỉ khi `OC_SEARCH_PROVIDER=searxng`) | không |
| 06 | *(bỏ qua được)* Kết nối Google bằng terminal | chỉ khi Drive là tài khoản của **bạn**; nếu là của khách, để khách tự kết nối qua chat |

Bước `02_install_hermes.sh` chạy `hermes setup` (wizard tương tác — chọn model/provider DeepSeek + Telegram) rồi `hermes gateway install --start-now --start-on-login` (systemd user service, native).

### Bước 03 và 06: nhập sẵn hay để khách tự làm?

Cả hai bước đều ghi vào đúng những chỗ mà skill `guided-setup` ghi, nên **chọn đường nào cũng
được và làm lại lúc nào cũng được**.

**Để khách tự làm qua chat (mặc định)** khi: key do khách trả tiền, Google Drive là tài khoản
của khách, hoặc bạn muốn buổi bàn giao có luôn phần "khách tự cài được".

**Nhập sẵn ở terminal** khi: bạn đã cầm key trong tay và muốn demo chạy được ngay từ phút đầu,
hoặc khách hoàn toàn không muốn tự thao tác.

### Bước 06 — Google: hai quyết định trước khi chạy đường terminal

1. **Chọn bộ quyền** (`OC_GOOGLE_SCOPES` trong `config.env`):
   - `minimal` (mặc định) — chỉ `drive.file`, bot **chỉ đụng được file do chính nó tạo**. Không có màn hình cảnh báo, dễ giải thích với khách. Đổi lại không đọc được link Google riêng tư người dùng dán vào.
   - `private-links` — thêm `drive.readonly` để đọc link riêng tư. Đây là scope **restricted**: người dùng phải bấm qua màn hình *"Google hasn't verified this app"*.
   (Đường chat hỏi đúng câu này bằng lời và mặc định chọn `minimal`.)
2. **PUBLISH APP trên màn hình OAuth consent.** Để ở chế độ *Testing* thì Google cho refresh token sống **đúng 7 ngày** — bot chạy ngon cả tuần rồi chết với `invalid_grant`. Script bắt gõ `published` để xác nhận, đừng gõ cho qua. Đường chat cũng nhấn mạnh đúng bước này.

Chi tiết từng màn hình Console, câu hỏi của khách về quyền riêng tư, bảng tra sự cố cho **cả hai đường**: [docs/google-oauth-setup.vi.md](../docs/google-oauth-setup.vi.md) · [EN](../docs/google-oauth-setup.en.md).

## Sau khi cài
1. Mở Telegram, chat `@your_bot`: **"Cài đặt giúp tôi"** → bot dẫn nốt phần key, Google, chủ đề và giờ gửi, rồi chạy thử một bản tin thật.
2. Thử D2: gửi 1 file .docx + *"Chuyển thành PowerPoint"* → nhận link Google Slides kèm PDF (cần đã kết nối Google).
3. Kiểm tra: `bash scripts/healthcheck_hermes.sh` → `"ok":true`.
4. Bàn giao theo `docs/handover-session.md`.

## Kiểm thử: 3 mức, từ rẻ tới thật

| Lệnh | Trả lời câu hỏi gì | Cần gì |
| --- | --- | --- |
| `python3 skills/guided-setup/scripts/selftest.py` | **Luồng cài đặt có chạy trơn không?** | không cần key, không cần mạng ra Google |
| `python3 skills/guided-setup/scripts/check_setup.py --verify` | **Key đang lưu có còn dùng được không?** | có mạng |
| Đóng vai người dùng nhắn *"Cài đặt giúp tôi"* | **Người thật có làm theo nổi không?** | tài khoản Google thật |

**Mức 1 — diễn tập (bước 04 tự chạy).** `selftest.py` chạy đúng các CLI mà bot sẽ chạy,
trên `HERMES_HOME` tạm và một Google giả ở localhost, rồi in ra bảng PASS/FAIL 14 dòng.
Nó bắt được: key dán lộn xộn có được nhận đúng không, dán nhầm địa chỉ web có bị chặn
không, link cấp quyền có xin `offline` + PKCE không, mã đổi token có gửi đúng tham số
không, `token.json` ghi ra có đọc được bằng thư viện của doc-convert không, và 3 kiểu hỏng
hay gặp (mã hết hạn, link cũ, không có refresh token) có báo thành câu sửa được không.
Không đụng gì tới bản cài đang chạy.

**Mức 2 — key thật.** `--verify` gọi thật tới từng nhà cung cấp, nên bắt được key đã bị xoá
hoặc hết hạn mức — thứ mà kiểm tra "có/không có key" không thấy. `healthcheck_hermes.sh`
cũng chạy sẵn kiểm tra này và báo trong trường `keys`.

**Mức 3 — Google thật + người thật.** Cái duy nhất hai mức trên không thay thế được là màn
hình consent thật và phản ứng của người dùng. Checklist 6 điểm + 2 tình huống hỏng nên thử:
[docs/google-oauth-setup.vi.md](../docs/google-oauth-setup.vi.md), mục **8b**. Làm luôn
trong buổi bàn giao là gọn nhất — vừa kiểm thử vừa là phần "khách tự thao tác được".

## Tuỳ chọn sau khi cài
- **Morning Report search**: skill dùng `exa` chính + `brave` dự phòng trong `collect_sources.py` (cần `EXA_API_KEY`, `BRAVE_SEARCH_API_KEY`, `FIRECRAWL_API_KEY` trong `~/.hermes/.env`). `OC_SEARCH_PROVIDER=searxng` chỉ kích hoạt bước 05 (SearXNG cho platform `web` tool của Hermes) — không ảnh hưởng search của skill.
- **Ảnh cho slide**: D2 tự lấy ảnh CC từ Openverse, không cần API key. Muốn tắt: `--no-auto-images`.
- **Đổi bộ quyền Google sau này**: bảo khách nhắn *"Kết nối lại Google, cho phép đọc link riêng tư"* — skill sẽ authorize lại với `private-links`. Đường terminal: sửa `DOC_CONVERT_GOOGLE_SCOPES` trong `~/.hermes/.env`, xoá `token.json`, chạy lại bước 06.

## Kiểm chứng đã làm
- Toàn bộ script `*_hermes.sh`: `bash -n` pass.
- Unit test trên Ubuntu: **125/125** (morning-report, gồm 26 test cầu nối D1→D2) + **69/69** (doc-convert) + **44/44** (guided-setup: 36 unit + 8 test đổi token qua HTTP thật với Google giả).
- Diễn tập luồng cài đặt `selftest.py`: **14/14 PASS**, không để lại gì trong repo lẫn bản cài.
- `config.env` phân giải đúng cho user bất kỳ (vd `ubuntu` → `/home/ubuntu`).
- `healthcheck_hermes.sh` chạy thật trên gateway → `ok:true`.
