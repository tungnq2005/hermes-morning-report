# Morning Brief Setup — OpenClaw (D1 + D2 + D3)

Bộ script + tài liệu để deploy trợ lý AI Telegram (OpenClaw, cài **NATIVE** không Docker) lên VPS Ubuntu, gồm cả 2 skill và tài liệu bàn giao.

- **D1 — Morning Report**: bot gửi bản tin sáng (text + audio 3–5 phút) qua cron.
- **D2 — Document Conversion**: chuyển đổi Word/PPT/PDF/Markdown + tường thuật audio.
- **D3 — Technical Setup**: provisioning, integration, giám sát, tài liệu, bàn giao.

## Cấu trúc

```
morning-brief-setup/
├── config.env                 <- SỬA TRƯỚC: user, port, timezone, giờ gửi, search provider
├── setup_all.sh               <- chạy tất cả các bước theo thứ tự
├── scripts/
│   ├── 01_system_prep.sh          cập nhật OS + gói nền D1 & D2 (LibreOffice, pip) + lingering
│   ├── 02_install_openclaw.sh     cài OpenClaw CLI + onboarding daemon (NATIVE)
│   ├── 03_setup_env.sh            tạo /etc/openclaw/openclaw.env (token + search key) + quyền 600
│   ├── 04_attach_env_service.sh   gắn env vào gateway service (drop-in)
│   ├── 05_migrate_secrets.sh      migrate secret sang SecretRef (non-interactive)
│   ├── 06_bootstrap_skill.sh      cài CẢ 2 skill từ ../skills/ + test + readiness
│   ├── 07_configure_integrations.sh  tool profile (tts/message) + search provider + command owner
│   ├── 08_searxng.sh              (tùy chọn) dựng SearXNG nếu chọn provider này
│   └── healthcheck.sh             kiểm tra sức khoẻ (bằng chứng ổn định 48h)
├── templates/                 <- mẫu env + systemd override
└── docs/
    ├── user-guide.vi.md / .en.md      hướng dẫn người dùng cuối (song ngữ)
    ├── operator-runbook.vi.md / .en.md  sổ tay vận hành cho quản trị (song ngữ)
    ├── chat-commands.md               bảng lệnh nhanh 1 trang (song ngữ)
    └── handover-session.md            kịch bản bàn giao 30 phút + checklist nghiệm thu
```

## Cách deploy lên VPS

```bash
# SSH vào VPS Ubuntu rồi clone repo này — bước 06 cài skill từ chính bản clone.
git clone https://github.com/tungnq2005/openclaw-morning_report.git
cd openclaw-morning_report/setup
chmod +x setup_all.sh scripts/*.sh

cp config.env.example config.env   # setup_all.sh source config.env, không phải .example
nano config.env                    # sửa OC_USER, OC_TIMEZONE, OC_DELIVERY_TIME, OC_SEARCH_PROVIDER...

./setup_all.sh         # chạy tuần tự, dừng xác nhận trước mỗi bước
```

Các bước tương tác (wizard) trong `02` (onboarding) đã ghi rõ lựa chọn trong script — **nhớ chọn systemd user service, KHÔNG Docker** để giữ tool browser.

## Sau khi cài
1. Mở Telegram, chat `@your_bot`: *"Setup Morning Report cho tôi bằng skill morning report."*
2. Thử D2: gửi 1 file .docx + *"Chuyển thành PowerPoint"*.
3. Kiểm tra: `bash scripts/healthcheck.sh` → `"ok":true`.
4. Bàn giao theo `docs/handover-session.md`.

## Tuỳ chọn sau khi cài
- **Search**: mặc định `brave` làm chính, `exa` làm dự phòng khi Brave trả 429 (cần `EXA_API_KEY`). Đổi `OC_SEARCH_PROVIDER` trong `config.env` nếu muốn `tavily`/`searxng`/`google`.
- **Google Workspace OAuth** (đọc file Google riêng tư + tạo draft thẳng vào Docs/Slides): chép `client_secret.json` vào `skills/doc-convert/state/google-creds/` rồi chạy một lần:
  ```bash
  python3 skills/doc-convert/scripts/authorize_google.py
  ```
  Bỏ qua bước này thì D2 vẫn chạy đầy đủ với file upload và link Google công khai.
- **Ảnh cho slide**: D2 tự lấy ảnh CC từ Openverse, không cần API key. Muốn tắt: `--no-auto-images`.

## Kiểm chứng đã làm
- Toàn bộ script: `bash -n` pass.
- Unit test trên Ubuntu: **90/90** (morning-report) + **29/29** (doc-convert).
- `config.env` phân giải đúng cho user bất kỳ (vd `ubuntu` → `/home/ubuntu`).
- `healthcheck.sh` chạy thật trên gateway dev → `ok:true`.
