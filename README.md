# OpenClaw Morning Report + Document Agent

Hai trợ lý AI chạy qua **Telegram bot** (nền tảng [OpenClaw](https://openclaw.ai), cài native trên VPS Ubuntu):

1. **Morning Report** — mỗi sáng bot tự tổng hợp tin theo chủ đề bạn chọn và gửi **bản chữ + audio 3–5 phút**. Đổi chủ đề / giờ gửi / phong cách bằng cách nhắn bot.
2. **Document Conversion** — gửi file (Word/PowerPoint/PDF/Markdown) hoặc link Google, bot **chuyển đổi hai chiều**, tạo draft thẳng vào **Google Docs/Slides**, hoặc **đọc thành audio**.

> Two Telegram-based AI agents on OpenClaw: a daily **Morning Report** (text + audio brief) and a **Document Conversion** agent (Word/PPT/PDF/Markdown + Google Workspace + narration).

---

## Tính năng chính

- 📰 Bản tin sáng tự động (cron), text + audio, đa chủ đề, đổi cấu hình qua chat
- 📄 Chuyển đổi tài liệu: docx ↔ pptx ↔ pdf ↔ md, tạo slide có layout nhất quán
- ☁️ Google Workspace: đọc Docs/Slides/Drive riêng tư, tạo draft trực tiếp trên cloud
- 🔊 Text-to-speech (Google TTS) cho cả bản tin lẫn tài liệu
- 🔒 Secrets tách khỏi code (SecretRef + env file), audit sạch plaintext
- 🖥️ Chạy native trên VPS (systemd), gửi qua Telegram long-polling — **không cần public IP/webhook**

## Kiến trúc

```
Telegram  ──long-polling──►  OpenClaw Gateway (native, systemd, 127.0.0.1)
                                 ├─ LLM: DeepSeek (SecretRef)
                                 ├─ Search: Brave / Tavily / SearXNG / Exa
                                 ├─ TTS: Google TTS → MP3
                                 └─ Skills:
                                      • morning-report  (D1)
                                      • doc-convert      (D2)
```

## Cấu trúc repo

```
skills/morning-report/   Skill bản tin sáng (D1)
skills/doc-convert/       Skill chuyển đổi tài liệu (D2)
setup/                    Script cài đặt VPS + config.env.example
docs/                     Hướng dẫn người dùng + vận hành (song ngữ VI/EN)
AGENTS.md                 Tài liệu workspace cho agent
```

## Cài đặt nhanh (VPS Ubuntu)

```bash
# 1. Copy repo lên VPS
scp -r openclaw-morning_report <user>@<IP_VPS>:~/

# 2. SSH vào, chuẩn bị config
cd ~/openclaw-morning_report/setup
sed -i 's/\r$//' setup_all.sh config.env.example scripts/*.sh
cp config.env.example config.env      # sửa OC_USER, timezone, giờ gửi, search provider
chmod +x setup_all.sh scripts/*.sh

# 3. Chạy (cài native, KHÔNG Docker)
./setup_all.sh
```

Chi tiết từng bước + wizard tương tác: xem [setup/README.md](setup/README.md).
Bạn tự cấp **secrets của mình** (Telegram bot token, DeepSeek/model key, Google OAuth) — repo không chứa secret nào.

## Tài liệu

- Người dùng cuối: [docs/user-guide.vi.md](docs/user-guide.vi.md) · [EN](docs/user-guide.en.md)
- Bảng lệnh nhanh: [docs/chat-commands.md](docs/chat-commands.md)
- Vận hành/quản trị: [docs/operator-runbook.vi.md](docs/operator-runbook.vi.md) · [EN](docs/operator-runbook.en.md)
- Bàn giao 30 phút: [docs/handover-session.md](docs/handover-session.md)

## Yêu cầu

- VPS Ubuntu 22.04/24.04+, ≥ 2GB RAM (LibreOffice + audio)
- Telegram bot token (@BotFather), model API key (DeepSeek…)
- (Tùy chọn) Google Cloud OAuth client cho tính năng Google Workspace

## Ghi công

- **D1 — Morning Report**: nghiathan13
- **D2 — Document Conversion**: tungnq2005

## Bảo mật

Không commit secret. `.gitignore` đã loại `state/`, `*.env`, `google-creds/`, `token.json`, `client_secret.json`. Mỗi lần deploy tự cấp secret riêng qua `/etc/openclaw/openclaw.env` (quyền 600, SecretRef).
