# Morning Brief Setup — Hermes Agent (D1 + D2 + D3)

Bộ script + tài liệu để deploy trợ lý AI Telegram (Hermes Agent, cài **NATIVE** không Docker) lên VPS Ubuntu, gồm cả 2 skill và tài liệu bàn giao.

- **D1 — Morning Report**: bot gửi bản tin sáng (text + audio 3–5 phút) qua cron, per-topic.
- **D2 — Document Conversion**: chuyển đổi Word/PPT/PDF/Markdown + tường thuật audio.
- **D3 — Technical Setup**: provisioning, integration, giám sát, tài liệu, bàn giao.

## Cấu trúc

```
openclaw-morning_report/
├── config.env                 <- SỬA TRƯỚC: user, timezone, giờ gửi, search provider (gate 08)
├── setup_all_hermes.sh        <- chạy tất cả các bước theo thứ tự
├── scripts/
│   ├── 01_system_prep_hermes.sh        cập nhật OS + gói nền D1 & D2 + xz-utils + lingering
│   ├── 02_install_hermes.sh            cài Hermes CLI + hermes setup (wizard) + gateway service (NATIVE)
│   ├── 03_setup_env_hermes.sh          ghi EXA/Firecrawl/Brave vào ~/.hermes/.env (mode 600)
│   ├── 04_bootstrap_skill_hermes.sh    symlink CẢ 2 skill từ ../skills/ + test + readiness
│   ├── 05_searxng_hermes.sh            (tùy chọn) SearXNG cho platform web tool (skill không cần)
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
git clone https://github.com/tungnq2005/openclaw-morning_report.git
cd openclaw-morning_report/setup
chmod +x setup_all_hermes.sh scripts/*.sh

cp config.env.example config.env   # setup_all_hermes.sh source config.env, không phải .example
nano config.env                    # sửa OC_USER, OC_TIMEZONE, OC_DELIVERY_TIME, OC_SEARCH_PROVIDER...

./setup_all_hermes.sh         # chạy tuần tự, dừng xác nhận trước mỗi bước
```

Bước `02_install_hermes.sh` chạy `hermes setup` (wizard tương tác — chọn model/provider DeepSeek + Telegram) rồi `hermes gateway install --start-now --start-on-login` (systemd user service, native).

## Sau khi cài
1. Mở Telegram, chat `@your_bot`: *"Setup Morning Report cho tôi bằng skill morning report."* (hoặc chạy `python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py --save --enable-cron`).
2. Thử D2: gửi 1 file .docx + *"Chuyển thành PowerPoint"* → nhận link Google Slides kèm PDF (cần đã authorize Google, xem mục bên dưới).
3. Kiểm tra: `bash scripts/healthcheck_hermes.sh` → `"ok":true`.
4. Bàn giao theo `docs/handover-session.md`.

## Tuỳ chọn sau khi cài
- **Morning Report search**: skill dùng `exa` chính + `brave` dự phòng trong `collect_sources.py` (cần `EXA_API_KEY`, `BRAVE_SEARCH_API_KEY`, `FIRECRAWL_API_KEY` trong `~/.hermes/.env`). `OC_SEARCH_PROVIDER=searxng` chỉ kích hoạt bước 05 (SearXNG cho platform `web` tool của Hermes) — không ảnh hưởng search của skill.
- **Google Workspace OAuth** — **nên làm, không phải tuỳ chọn thực sự**: D2 dựng kết quả trên Google Slides/Docs rồi export file từ đó, nhờ vậy mở trên macOS/Windows/iPad đều giống nhau. Hướng dẫn đầy đủ từng bước (kể cả bước **PUBLISH APP** mà bỏ qua là bot chết sau 7 ngày): [docs/google-oauth-setup.vi.md](../docs/google-oauth-setup.vi.md) · [EN](../docs/google-oauth-setup.en.md). Tóm tắt: chép `client_secret.json` vào `skills/doc-convert/state/google-creds/` rồi chạy:
  ```bash
  python3 skills/doc-convert/scripts/authorize_google.py
  ```
  Bỏ qua thì D2 vẫn convert được nhưng render bằng python-pptx/LibreOffice (kèm cảnh báo `google_unauthorized:rendered_locally`), và file .pptx có thể hiển thị lệch trong PowerPoint trên Mac; `--to gslides/gdoc` sẽ báo lỗi.
- **Ảnh cho slide**: D2 tự lấy ảnh CC từ Openverse, không cần API key. Muốn tắt: `--no-auto-images`.

## Kiểm chứng đã làm
- Toàn bộ script `*_hermes.sh`: `bash -n` pass.
- Unit test trên Ubuntu: **73/73** (morning-report) + **29/29** (doc-convert).
- `config.env` phân giải đúng cho user bất kỳ (vd `ubuntu` → `/home/ubuntu`).
- `healthcheck_hermes.sh` chạy thật trên gateway → `ok:true`.
