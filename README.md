# Hermes Morning Report + Document Agent

Hai trợ lý AI chạy qua **Telegram bot** (nền tảng **Hermes**, cài native trên VPS Ubuntu):

1. **Morning Report** — mỗi sáng bot tự tổng hợp tin theo chủ đề bạn chọn và gửi **bản chữ + audio 3–5 phút**. Đổi chủ đề / giờ gửi / phong cách bằng cách nhắn bot.
2. **Document Conversion** — gửi file (Word/PowerPoint/PDF/Markdown) hoặc link Google, bot dựng kết quả **thẳng trên Google Slides/Docs** (kèm bản PDF), hoặc **đọc thành audio**. File Office (.pptx/.docx) nếu cần đều được **export ra từ chính file Google** nên mở trên Mac hay Windows đều giống nhau.

Hai tính năng nối thẳng vào nhau: **bản tin sáng chính là một đầu vào của phần chuyển đổi**. Nhắn *"Xuất bản tin sáng nay ra Google Docs"* hay *"Làm slide từ bản tin crypto hôm qua"* là bot lấy đúng bản tin đã lưu rồi dựng file — người dùng không phải gửi lại gì cả.

> Two Telegram-based AI agents on Hermes: a daily **Morning Report** (text + audio brief) and a **Document Conversion** agent that delivers **Google Slides/Docs** (plus Google-exported .pptx/.docx/.pdf) and narration.

---

## Tính năng chính

- 🧭 **Cài đặt ngay trong chat**: bot dẫn người dùng lấy từng API key và kết nối Google, họ dán key vào Telegram — không terminal, không SSH tunnel
- 📰 Bản tin sáng tự động (cron), text + audio, đa chủ đề, đổi cấu hình qua chat
- 📄 Chuyển đổi tài liệu: docx ↔ pptx ↔ pdf ↔ md, slide có layout nhất quán (cover, section divider, thẻ số liệu, ảnh minh họa)
- 🔗 **Bản tin → tài liệu**: xuất bất kỳ bản tin nào đã nhận (hôm nay hay tuần trước) ra Google Docs/Slides/PDF chỉ bằng một câu nhắn; xuất lại lần hai trả về đúng file cũ thay vì tạo bản trùng trong Drive. Muốn tự động thì bật *"lưu bản tin vào Google Docs"* cho từng chủ đề
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
                                      • guided-setup     (cài đặt & kết nối key qua chat)
                                      • morning-report  (D1)
                                      • doc-convert      (D2)
```

## Cấu trúc repo

```
skills/guided-setup/      Skill dẫn người dùng lấy key + kết nối Google ngay trong chat
skills/morning-report/   Skill bản tin sáng (D1)
skills/doc-convert/       Skill chuyển đổi tài liệu (D2)
setup/                    Script cài đặt: VPS Ubuntu (setup_all_hermes.sh)
                          + macOS desktop (install-mac.sh, install-doc-addon.sh, lib/)
docs/                     Hướng dẫn người dùng + vận hành (song ngữ VI/EN)
SOUL.md                   Tài liệu Hermes agent
```

## Hai đường cài đặt (chọn 1)

| | **VPS Ubuntu** | **macOS desktop luôn bật** |
|---|---|---|
| Script | `setup/setup_all_hermes.sh` | `setup/install-mac.sh` |
| Service | systemd user + linger | launchd LaunchAgent |
| Ưu điểm | Chạy 24/7 không cần ai đăng nhập | Dùng máy khách hàng đã có, không phí hosting |
| Ràng buộc | Phí VPS hàng tháng | Máy phải **bật + đang đăng nhập**; reboot phải đăng nhập lại |
| Tài liệu | [setup/README.md](setup/README.md) | [docs/install-mac.md](docs/install-mac.md) (EN) |

Không có đường nào là "mặc định khuyến nghị": VPS ổn định hơn, macOS tận dụng hardware
có sẵn. Tài liệu macOS viết bằng tiếng Anh cho khách hàng cuối.

## Cài đặt nhanh (VPS Ubuntu)

```bash
# 1. Copy repo lên VPS
scp -r hermes-morning-report <user>@<IP_VPS>:~/

# 2. SSH vào, chuẩn bị config
cd ~/hermes-morning-report/setup
sed -i 's/\r$//' setup_all_hermes.sh config.env.example scripts/*.sh
cp config.env.example config.env      # sửa OC_USER, timezone, giờ gửi, search provider
chmod +x setup_all_hermes.sh scripts/*.sh

# 3. Chạy (cài native, KHÔNG Docker)
./setup_all_hermes.sh
```

Xong phần máy chủ, **phần còn lại làm trong chat**: mở Telegram nhắn bot

> **Cài đặt giúp tôi**

Bot kiểm tra còn thiếu gì, dẫn từng bước tạo API key (Exa / Firecrawl / Brave) và kết nối Google Workspace, nhận key người dùng **dán vào chat**, tự kiểm tra với nhà cung cấp rồi lưu vào `~/.hermes/.env` (quyền 600). Kết nối Google **không cần SSH tunnel**: bot gửi link, người dùng bấm Cho phép rồi dán lại đường link trên thanh địa chỉ. Người cài **không phải cầm key của khách**.

Chi tiết từng bước + wizard tương tác: xem [setup/README.md](setup/README.md).
Mọi **secret là của người dùng** (Telegram bot token, DeepSeek/model key, **Exa, Firecrawl & Brave (optional) API keys**, Google OAuth) — repo không chứa secret nào.

## Install on an always-on Mac (English)

For a Mac Studio / Mac mini that stays powered on and logged in. One command installs
**both** skills — the morning report first, then document conversion:

```bash
curl -fsSL https://<host>/install-mac.sh | bash
```

It asks for the 4 API keys, validates each one on the spot, installs the gateway as a
LaunchAgent, turns off system sleep, installs a watchdog that alerts Telegram directly
if the bot dies, and finishes with a real report delivered through the real cron path.

Read before installing: [docs/install-mac.md](docs/install-mac.md) ·
limits: [docs/limits-mac.md](docs/limits-mac.md) ·
when something breaks: [docs/troubleshoot-mac.md](docs/troubleshoot-mac.md)

Do **not** use `setup_all_hermes.sh` on macOS — it is Ubuntu-only (`apt`, `systemd`,
`getent`).

## Tài liệu

- Cài trên macOS (EN): [docs/install-mac.md](docs/install-mac.md) · [limits](docs/limits-mac.md) · [troubleshooting](docs/troubleshoot-mac.md)
- Người dùng cuối: [docs/user-guide.vi.md](docs/user-guide.vi.md) · [EN](docs/user-guide.en.md)
- **Cài đặt qua chat (đường mặc định)**: [docs/first-run-setup.vi.md](docs/first-run-setup.vi.md) · [EN](docs/first-run-setup.en.md)
- **Kết nối Google (bắt buộc cho D2)**: [docs/google-oauth-setup.vi.md](docs/google-oauth-setup.vi.md) · [EN](docs/google-oauth-setup.en.md)
- Bảng lệnh nhanh: [docs/chat-commands.md](docs/chat-commands.md)
- Vận hành/quản trị: [docs/operator-runbook.vi.md](docs/operator-runbook.vi.md) · [EN](docs/operator-runbook.en.md)
- Bàn giao 30 phút: [docs/handover-session.md](docs/handover-session.md)

## Yêu cầu

- VPS Ubuntu 22.04/24.04+, ≥ 2GB RAM (LibreOffice + audio)
- Telegram bot token (@BotFather) + model API key (DeepSeek…) — nhập lúc cài, ở bước 02
- Exa API key cho Morning Report; Firecrawl & Brave nên có; Google Cloud OAuth client nếu cần Google Slides/Docs — **tất cả những cái này lấy được ngay trong chat**, xem [docs/first-run-setup.vi.md](docs/first-run-setup.vi.md)


## Bảo mật

Không commit secret. `.gitignore` đã loại `state/`, `*.env`, `google-creds/`, `token.json`, `client_secret.json`. Mỗi lần deploy tự cấp secret riêng qua `~/.hermes/.env` (quyền 600).
