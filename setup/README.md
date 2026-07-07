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
│   ├── 06_bootstrap_skill.sh      cài CẢ 2 skill (morning-report + doc-convert) + test + preflight
│   ├── 07_configure_integrations.sh  tool profile (tts/message) + search provider + command owner
│   ├── 08_searxng.sh              (tùy chọn) dựng SearXNG nếu chọn provider này
│   └── healthcheck.sh             kiểm tra sức khoẻ (bằng chứng ổn định 48h)
├── skills-local/doc-convert/  <- skill D2 (đóng gói local, không có trong repo upstream)
├── overlays/                  <- bản vá đè lên skill upstream (fix media-path audio-runtime.md)
├── templates/                 <- mẫu env + systemd override
└── docs/
    ├── user-guide.vi.md / .en.md      hướng dẫn người dùng cuối (song ngữ)
    ├── operator-runbook.vi.md / .en.md  sổ tay vận hành cho quản trị (song ngữ)
    ├── chat-commands.md               bảng lệnh nhanh 1 trang (song ngữ)
    └── handover-session.md            kịch bản bàn giao 30 phút + checklist nghiệm thu
```

## Cách deploy lên VPS

```powershell
# Từ Windows, copy bộ script lên VPS:
scp -r C:\Users\Tung\morning-brief-setup <user>@IP_VPS:~/
```

```bash
# SSH vào VPS rồi:
cd ~/morning-brief-setup
sed -i 's/\r$//' setup_all.sh config.env scripts/*.sh    # bỏ CRLF của Windows
chmod +x setup_all.sh scripts/*.sh

nano config.env        # sửa OC_USER, OC_TIMEZONE, OC_DELIVERY_TIME, OC_SEARCH_PROVIDER...

./setup_all.sh         # chạy tuần tự, dừng xác nhận trước mỗi bước
```

Các bước tương tác (wizard) trong `02` (onboarding) đã ghi rõ lựa chọn trong script — **nhớ chọn systemd user service, KHÔNG Docker** để giữ tool browser.

## Sau khi cài
1. Mở Telegram, chat `@tungnq_bot`: *"Setup Morning Report cho tôi bằng skill morning report."*
2. Thử D2: gửi 1 file .docx + *"Chuyển thành PowerPoint"*.
3. Kiểm tra: `bash scripts/healthcheck.sh` → `"ok":true`.
4. Bàn giao theo `docs/handover-session.md`.

## ⚠️ 2 quyết định cần chốt (xem plan D3)
- **Search provider**: Brave free bị rate-limit (429). Chọn Tavily / SearXNG / Brave-trả-phí / Google PSE → set `OC_SEARCH_PROVIDER` trong `config.env`.
- **Google Workspace OAuth** (đọc Google riêng tư + tạo draft thẳng vào Slides/Docs): hiện chưa có; cân nhắc làm ngay hay hoãn phase 2.

## Kiểm chứng đã làm
- Toàn bộ script: `bash -n` pass.
- Skill D2 đóng gói: 10/10 unit test pass trên Ubuntu.
- `config.env` phân giải đúng cho user bất kỳ (vd `ubuntu` → `/home/ubuntu`).
- `healthcheck.sh` chạy thật trên gateway dev → `ok:true`.
