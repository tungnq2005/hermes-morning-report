# Sổ tay vận hành (Operator Runbook)

Dành cho người quản trị VPS. Người dùng cuối **không cần** đọc tài liệu này.

## Kiến trúc tổng quan

```
Telegram (người dùng)
      │  long-polling (không cần public IP / webhook)
      ▼
Hermes Gateway  ── cài NATIVE, systemd user service (hermes-gateway.service)
  ├─ Model LLM: DeepSeek (DEEPSEEK_API_KEY trong ~/.hermes/.env)
  ├─ Search (skill Morning Report): Exa chính + Brave fallback
  ├─ TTS: Google Translate endpoint (keyless) → MP3
  ├─ Tools: tts/web/browser/terminal… (hermes tools list)
  └─ Skills:
       • morning-report (D1): cron per-topic gửi bản tin sáng
       • doc-convert   (D2): LibreOffice + python-docx/pptx/pypdf
```

**Cài NATIVE** (theo bộ setup này). Lưu ý: Hermes Docker image chính thức cũng có tool browser, nhưng bộ setup này dùng native.

## Vị trí file quan trọng

| Mục | Đường dẫn |
|---|---|
| Secrets (token/key) | `~/.hermes/.env` (quyền 600) |
| Config Hermes | `~/.hermes/config.yaml` |
| Skills | `~/.hermes/skills/` (symlink từ repo `openclaw-morning_report/skills/`) |
| Lịch sử bản tin (per-topic, manifest.json/run) | `~/.hermes/skills/productivity/morning-report/state/history/` |
| Output cron run | `~/.hermes/cron/output/<job-id>/` |
| Log gateway | `journalctl --user -u hermes-gateway.service` (hoặc `hermes logs`) |
| Bộ script + docs | thư mục `openclaw-morning_report/` (repo) |

> Hermes tự load `~/.hermes/.env` qua `HERMES_HOME` — không cần nạp env thủ công. Skill cũng tự load `.env` mỗi run.

## Thao tác thường gặp

```bash
# Trạng thái + sức khoẻ
systemctl --user status hermes-gateway.service
hermes gateway status --deep
bash openclaw-morning_report/setup/scripts/healthcheck_hermes.sh   # JSON ok/problems

# Khởi động lại gateway
hermes gateway restart

# Xem log trực tiếp
journalctl --user -u hermes-gateway.service -f

# Cron bản tin sáng (per-topic: "Morning Report - <topic>")
hermes cron list --all              # xem job + Last run + giờ kế
hermes cron run <job-id>            # ép chạy ngay (debug)
ls -t ~/.hermes/cron/output/<job-id>/ | head -1   # output run mới nhất

# Health / audit
hermes doctor                       # All checks passed = sạch
hermes security audit               # supply-chain (OSV.dev)
```

## Đổi API key / token

1. Sửa giá trị trong `~/.hermes/.env` (nano, **không cần sudo** — file của user, quyền 600).
   - Search keys (EXA/FIRECRAWL/BRAVE): skill tự load mỗi run → không cần restart.
   - Telegram/DeepSeek: cần restart gateway (bước 2).
2. `hermes gateway restart`
3. `hermes doctor` để chắc chắn setup khỏe.

Hermes lưu secret trong `~/.hermes/.env` (mode 600); `config.yaml` không chứa plaintext. Đổi giá trị trong `.env` là xong.

## Đổi giờ gửi / múi giờ bản tin (per-topic)

Cách đơn giản: nhắn bot *"Đổi [topic] sang 7h sáng"* (skill Update Config, per-topic).
Cách CLI (qua skill, reconcile cron jobs):
```bash
python3 ~/.hermes/skills/productivity/morning-report/scripts/prepare_config.py \
  --topic "<topic>" --delivery-time "07:00" --save --enable-cron
```

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Bot không phản hồi | Gateway chết / mất mạng | `hermes gateway restart`; xem `journalctl --user -u hermes-gateway.service` |
| Bản tin nghèo nguồn, log có `429` | Exa/Brave bị rate-limit | Skill tự fallback Exa→Brave. Nếu cả hai 429: kiểm `EXA_API_KEY`/`BRAVE_SEARCH_API_KEY` trong `~/.hermes/.env`; thử lại sau. (Platform web tool: `hermes config set web.search_backend` + `05_searxng_hermes.sh` optional) |
| Không gửi được audio MP3 | MEDIA path / Deliver / tts | `hermes tools list` (tts mặc định enabled). `hermes cron list --all` (Deliver: origin). MP3 do skill ghi vào `~/.hermes/skills/.../state/history/<run>/` |
| `hermes doctor` báo issue | Config/dep thiếu | `hermes doctor --fix` (thử tự sửa) hoặc xem output |
| Người lạ nhắn bot bị chặn | Pairing / allowed users | `hermes pairing approve <code>`; hoặc set `TELEGRAM_ALLOWED_USERS` trong `~/.hermes/.env` rồi `hermes gateway restart` |
| Sau reboot VPS bot im | Lingering chưa bật | `sudo loginctl enable-linger <user>` |
| Cron báo "LLM request failed" | Run >9 phút bị watchdog hủy (model `pro` compose lâu + search 429) | `hermes config set model deepseek/deepseek-v4-flash` + `hermes fallback add` (chọn pro); sửa search 429. KHÔNG phải lỗi key/balance |

## Nghiệm thu "ổn định 48h" (AC của D3)

1. Reboot VPS → xác nhận gateway TỰ lên: `systemctl --user is-active hermes-gateway.service` = active.
2. Theo dõi 48h, kiểm mỗi ngày:
   - `hermes cron list --all` → mỗi topic có run sáng thành công (Last run: ok).
   - `~/.hermes/skills/productivity/morning-report/state/history/` có run mới (manifest.json theo ngày).
   - `bash setup/scripts/healthcheck_hermes.sh` → `"ok":true`.
   - `hermes doctor` → All checks passed.
3. (Tùy chọn) đặt cron (`hermes cron create`) gọi `healthcheck_hermes.sh` mỗi vài giờ, gửi cảnh báo Telegram nếu `ok:false`.

## Google Workspace (D2)

- Credentials: `~/.hermes/skills/doc-convert/state/google-creds/` (symlink → repo) gồm `client_secret.json` + `token.json` (refresh token, quyền 600). `.gitignore='*'` nên không lọt repo.
- Authorize lại: `python3 ~/.hermes/skills/doc-convert/scripts/authorize_google.py --port 8765` (VPS headless: SSH tunnel `ssh -L 8765:localhost:8765 <user>@<vps>`).
- Cần enable Google Cloud Console: **Drive API + Docs API + Slides API**. Consent Testing → tài khoản phải nằm trong Test users.
- Kiểm tra: `python3 ~/.hermes/skills/doc-convert/scripts/preflight.py --compact` → `google.authorized_token: true`.
- Khả năng: đọc Docs/Slides/Drive riêng tư; tạo draft Google Docs (`--to gdoc`) / Slides (`--to gslides`).

## Known limitations

- **TTS keyless**: dùng endpoint Google Translate không chính thức, có thể bị chặn/đổi. Nâng cấp: Google Cloud TTS (có key) hoặc `edge-tts`.
- **Ảnh minh họa slide (D2)**: phụ thuộc search provider; nếu search giới hạn thì slide có thể thiếu ảnh.
- **OAuth client secret**: đã từng dán qua chat khi setup — nên rotate lại trong Google Cloud Console sau bàn giao.
