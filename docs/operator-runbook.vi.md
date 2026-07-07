# Sổ tay vận hành (Operator Runbook)

Dành cho người quản trị VPS. Người dùng cuối **không cần** đọc tài liệu này.

## Kiến trúc tổng quan

```
Telegram (người dùng)
      │  long-polling (không cần public IP / webhook)
      ▼
OpenClaw Gateway  ── cài NATIVE, systemd user service, bind 127.0.0.1:18789
  ├─ Model LLM: DeepSeek (key qua SecretRef)
  ├─ Search: <provider> (Brave/Tavily/SearXNG…)
  ├─ TTS: Google Translate endpoint (keyless) → MP3
  ├─ Tool browser (chỉ có khi cài NATIVE, không Docker)
  └─ Skills:
       • morning-report (D1): cron gửi bản tin sáng
       • doc-convert   (D2): LibreOffice + python-docx/pptx/pypdf
```

**Cài NATIVE, không Docker** — Docker sẽ làm mất tool browser của OpenClaw.

## Vị trí file quan trọng

| Mục | Đường dẫn |
|---|---|
| Secrets (token/key) | `/etc/openclaw/openclaw.env` (quyền 600) |
| Config gateway | `~/.openclaw/openclaw.json` |
| Drop-in nạp env vào service | `~/.config/systemd/user/openclaw-gateway.service.d/override.conf` |
| Workspace skills | `~/.openclaw/workspace/skills/` |
| Lịch sử bản tin (bằng chứng chạy) | `~/.openclaw/workspace/skills/morning-report/state/report-history/` |
| Audit log skill | `~/.openclaw/workspace/skills/morning-report/state/audit.log` |
| Log gateway | `journalctl --user -u openclaw-gateway.service` |
| Bộ script + docs | thư mục `morning-brief-setup/` |

> Mọi lệnh `openclaw` cần env đã nạp: `set -a; . /etc/openclaw/openclaw.env; set +a`
> (Đã thêm auto-load vào `~/.bashrc`, nên mở terminal mới là có sẵn.)

## Thao tác thường gặp

```bash
# Trạng thái + sức khoẻ
systemctl --user status openclaw-gateway.service
openclaw gateway status
bash morning-brief-setup/scripts/healthcheck.sh     # in JSON ok/problems

# Khởi động lại gateway
systemctl --user restart openclaw-gateway.service

# Xem log trực tiếp
journalctl --user -u openclaw-gateway.service -f

# Cron bản tin sáng
openclaw cron list                 # xem job + giờ chạy kế tiếp
openclaw cron runs <job-id>        # lịch sử các lần chạy
openclaw cron run <job-id>         # ép chạy ngay (debug)

# Secrets
openclaw secrets audit --check     # phải: clean, plaintext=0
```

## Đổi API key / token

1. Sửa giá trị trong `/etc/openclaw/openclaw.env` (nano, quyền sudo).
2. `systemctl --user restart openclaw-gateway.service`
3. `openclaw secrets audit --check` để chắc chắn không rớt về plaintext.
Vì config dùng SecretRef trỏ vào biến env, chỉ cần đổi giá trị trong env file là xong — không đụng `openclaw.json`.

## Đổi giờ gửi / múi giờ bản tin
Cách đơn giản: nhắn bot *"Đổi giờ gửi sang 7h sáng"*. Cách CLI: `openclaw cron edit <job-id>` (xem `openclaw cron edit --help`).

## Xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Bot không phản hồi | Gateway chết / mất mạng | `systemctl --user restart openclaw-gateway.service`; xem log |
| Bản tin nghèo nguồn, log có `429 RATE_LIMITED` | Search provider (Brave free) bị giới hạn | Đổi provider: sửa `OC_SEARCH_PROVIDER` + chạy `07_configure_integrations.sh`; hoặc dựng SearXNG (`08_searxng.sh`) |
| Không sinh được audio / không gửi được MP3 | Thiếu tool `tts`/`message`, hoặc gửi file từ ngoài workspace | Chạy `07_configure_integrations.sh` (mở `tools.alsoAllow`); MP3 phải nằm trong workspace, không dùng `/tmp` |
| `secrets audit` báo plaintext | Key mới chưa migrate | Chạy lại `05_migrate_secrets.sh` |
| Người lạ nhắn bot bị chặn | Cơ chế pairing | `openclaw pairing approve telegram <code>` |
| Sau reboot VPS bot im | Lingering chưa bật | `sudo loginctl enable-linger <user>` |
| Cron báo "LLM request failed" | Run chạy >9 phút bị watchdog hủy (thường do model reasoning `pro` compose lâu + search 429 kéo dài) | Dùng model nhanh làm default: `openclaw models set deepseek/deepseek-v4-flash` + `openclaw models fallbacks add deepseek/deepseek-v4-pro`; và sửa search 429. KHÔNG phải lỗi key/balance (kiểm bằng `curl .../user/balance`) |

## Nghiệm thu "ổn định 48h" (AC của D3)
1. Reboot VPS → xác nhận gateway TỰ lên: `systemctl --user is-active openclaw-gateway.service` = active.
2. Theo dõi 48h, kiểm mỗi ngày:
   - `openclaw cron runs <job-id>` → có run 7h sáng thành công.
   - `report-history/` có thư mục mới theo ngày.
   - `bash scripts/healthcheck.sh` → `"ok":true`.
   - `openclaw secrets audit --check` → clean.
3. (Tùy chọn) đặt cron OpenClaw gọi `healthcheck.sh` mỗi vài giờ, gửi cảnh báo Telegram cho operator nếu `ok:false`.

## Google Workspace (D2 — đã cấu hình)
- Credentials: `~/.openclaw/workspace/skills/doc-convert/state/google-creds/` gồm `client_secret.json` (OAuth desktop client) + `token.json` (refresh token, quyền 600). Thư mục có `.gitignore='*'` nên không bao giờ lọt vào repo/bundle.
- Authorize lại (khi token hỏng / đổi tài khoản): `python3 skills/doc-convert/scripts/authorize_google.py --port 8765` (VPS headless dùng SSH tunnel `ssh -L 8765:localhost:8765 <user>@<vps>`).
- Cần enable trong Google Cloud Console: **Drive API + Docs API + Slides API**. Consent screen ở chế độ Testing thì tài khoản phải nằm trong Test users.
- Kiểm tra: `python3 skills/doc-convert/scripts/preflight.py --compact` → mục `google.authorized_token: true`.
- Khả năng: đọc Docs/Slides/Drive **riêng tư**; tạo draft thẳng vào Google Docs (`--to gdoc`) / Slides (`--to gslides`).

## Known limitations
- **TTS keyless**: dùng endpoint Google Translate không chính thức, có thể bị chặn/đổi bất ngờ. Nâng cấp: Google Cloud TTS (có key) hoặc `edge-tts`.
- **Ảnh minh họa slide (D2)**: phụ thuộc search provider; nếu search bị giới hạn thì slide có thể thiếu ảnh.
- **OAuth client secret**: đã từng dán qua chat trong lúc setup — nên rotate lại trong Google Cloud Console sau khi bàn giao.
