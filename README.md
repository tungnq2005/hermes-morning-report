# Hermes Morning Report + Document Agent

Hai trợ lý AI chạy qua **Telegram bot** (nền tảng **Hermes**, cài native trên VPS Ubuntu):

1. **Morning Report** — mỗi sáng bot tự tổng hợp tin theo chủ đề bạn chọn và gửi **bản chữ + audio 3–5 phút**. Đổi chủ đề / giờ gửi / phong cách bằng cách nhắn bot.
2. **Document Conversion** — gửi file (Word/PowerPoint/PDF/Markdown) hoặc link Google, bot dựng kết quả **thẳng trên Google Slides/Docs** (kèm bản PDF), hoặc **đọc thành audio**. File Office (.pptx/.docx) nếu cần đều được **export ra từ chính file Google** nên mở trên Mac hay Windows đều giống nhau.

> Two Telegram-based AI agents on Hermes: a daily **Morning Report** (text + audio brief) and a **Document Conversion** agent that delivers **Google Slides/Docs** (plus Google-exported .pptx/.docx/.pdf) and narration.

---

## Tính năng chính

- 📰 Bản tin sáng tự động (cron), text + audio, đa chủ đề, đổi cấu hình qua chat
- 📄 Chuyển đổi tài liệu: docx ↔ pptx ↔ pdf ↔ md, slide có layout nhất quán (cover, section divider, thẻ số liệu, ảnh minh họa)
- ☁️ Google Workspace là renderer chính: kết quả nằm trên Google Slides/Docs, hiển thị y hệt trên macOS/Windows/iPad; đọc được Docs/Slides/Drive riêng tư
- 🔊 Text-to-speech (Google TTS) cho cả bản tin lẫn tài liệu
- 🔒 Secrets tách khỏi code (`~/.hermes/.env`, quyền 600), không plaintext trong config.yaml
- 🖥️ Chạy native trên VPS (systemd), gửi qua Telegram long-polling — **không cần public IP/webhook**

## Kiến trúc

```
Telegram  ──long-polling──►  Hermes Gateway (native, systemd, 127.0.0.1)
                                 ├─ LLM: DeepSeek (key trong ~/.hermes/.env)
                                 ├─ Search: Brave / Tavily / SearXNG / Exa  ·  Fetch: Firecrawl
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
SOUL.md                   Tài liệu Hermes agent
```

## Cài đặt nhanh (VPS Ubuntu)

```bash
# 1. Copy repo lên VPS
scp -r openclaw-morning_report <user>@<IP_VPS>:~/

# 2. SSH vào, chuẩn bị config
cd ~/openclaw-morning_report/setup
sed -i 's/\r$//' setup_all_hermes.sh config.env.example scripts/*.sh
cp config.env.example config.env      # sửa OC_USER, timezone, giờ gửi, search provider
chmod +x setup_all_hermes.sh scripts/*.sh

# 3. Chạy (cài native, KHÔNG Docker)
./setup_all_hermes.sh
```

Chi tiết từng bước + wizard tương tác: xem [setup/README.md](setup/README.md).
Bạn tự cấp **secrets của mình** (Telegram bot token, DeepSeek/model key, **Exa, Firecrawl & Brave (optional) API keys**, Google OAuth) — repo không chứa secret nào.

## Tài liệu

- Người dùng cuối: [docs/user-guide.vi.md](docs/user-guide.vi.md) · [EN](docs/user-guide.en.md)
- Bảng lệnh nhanh: [docs/chat-commands.md](docs/chat-commands.md)
- Vận hành/quản trị: [docs/operator-runbook.vi.md](docs/operator-runbook.vi.md) · [EN](docs/operator-runbook.en.md)
- Bàn giao 30 phút: [docs/handover-session.md](docs/handover-session.md)

## Yêu cầu

- VPS Ubuntu 22.04/24.04+, ≥ 2GB RAM (LibreOffice + audio)
- Telegram bot token (@BotFather), model API key (DeepSeek…), Exa & Firecrawl API keys (cho Morning Report)
- (Tùy chọn) Google Cloud OAuth client cho tính năng Google Workspace


## Bảo mật

Không commit secret. `.gitignore` đã loại `state/`, `*.env`, `google-creds/`, `token.json`, `client_secret.json`. Mỗi lần deploy tự cấp secret riêng qua `~/.hermes/.env` (quyền 600).
