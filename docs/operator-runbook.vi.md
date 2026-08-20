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
       • guided-setup      : dẫn người dùng lấy key + kết nối Google ngay trong chat
       • morning-report (D1): cron per-topic gửi bản tin sáng
       • doc-convert   (D2): LibreOffice + python-docx/pptx/pypdf
```

**Người dùng tự cấu hình được qua chat.** `guided-setup` ghi `EXA_API_KEY`,
`FIRECRAWL_API_KEY`, `BRAVE_SEARCH_API_KEY` vào `~/.hermes/.env` (600) và dựng
`client_secret.json` + `token.json` trong thư mục creds — đúng những chỗ mà bước 03/06 của
bộ setup ghi. Khi khách báo "bot bảo thiếu key", việc của bạn thường chỉ là bảo họ nhắn
*"Cài đặt giúp tôi"*, không phải SSH vào máy.

**Cài NATIVE** (theo bộ setup này). Lưu ý: Hermes Docker image chính thức cũng có tool browser, nhưng bộ setup này dùng native.

## Vị trí file quan trọng

| Mục | Đường dẫn |
|---|---|
| Secrets (token/key) | `~/.hermes/.env` (quyền 600) |
| Config Hermes | `~/.hermes/config.yaml` |
| Skills | `~/.hermes/skills/` (symlink từ repo `hermes-morning-report/skills/`) |
| Lịch sử bản tin (per-topic, manifest.json/run) | `~/.hermes/skills/productivity/morning-report/state/history/` |
| Output cron run | `~/.hermes/cron/output/<job-id>/` |
| Log gateway | `journalctl --user -u hermes-gateway.service` (hoặc `hermes logs`) |
| Bộ script + docs | thư mục `hermes-morning-report/` (repo) |

> Hermes tự load `~/.hermes/.env` qua `HERMES_HOME` — không cần nạp env thủ công. Skill cũng tự load `.env` mỗi run.

## Thao tác thường gặp

```bash
# Trạng thái + sức khoẻ
systemctl --user status hermes-gateway.service
hermes gateway status --deep
bash hermes-morning-report/setup/scripts/healthcheck_hermes.sh   # JSON ok/problems

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

**Cách nhanh nhất (search keys): để người dùng tự làm trong chat** — *"Mình có key Exa
mới, đổi giúp mình"*. Skill kiểm tra key với nhà cung cấp trước khi ghi đè, nên không có
chuyện lưu nhầm một key hỏng. Xem trạng thái không cần chat:

```bash
python3 ~/.hermes/skills/guided-setup/scripts/check_setup.py --verify
```

Bằng tay:

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
| Bot báo thiếu key / key hỏng / chưa kết nối Google | Cấu hình của người dùng, không phải hạ tầng | Bảo khách nhắn *"Cài đặt giúp tôi"*. Muốn tự kiểm: `python3 ~/.hermes/skills/guided-setup/scripts/check_setup.py --verify` |
| Bản tin nghèo nguồn, log có `429` | Exa/Brave bị rate-limit | Skill tự fallback Exa→Brave. Nếu cả hai 429: kiểm `EXA_API_KEY`/`BRAVE_SEARCH_API_KEY` trong `~/.hermes/.env`; thử lại sau. (Platform web tool: `hermes config set web.search_backend` + `05_searxng_hermes.sh` optional) |
| "Xuất bản tin ra Google Docs" không ra link | Chưa kết nối Google (bản tin vẫn gửi bình thường) | Bảo khách nhắn *"Kết nối Google giúp tôi"*. Kiểm nhanh: `python3 ~/.hermes/skills/productivity/morning-report/scripts/export_report.py --list` (xem bản tin nào đã lưu) và `preflight.py --compact` → `google.authorized_token` |
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
- Cài từ đầu (tạo project, bật API, **PUBLISH APP**, tạo client, authorize, kiểm tra, sự cố thường gặp): [google-oauth-setup.vi.md](google-oauth-setup.vi.md).
- **Đường mặc định là qua chat**: khách nhắn *"Kết nối Google giúp tôi"* → skill `guided-setup` dẫn hết, không cần SSH tunnel (mã cấp quyền lấy từ thanh địa chỉ của trang loopback báo lỗi). Đường terminal chỉ dùng khi Drive là tài khoản của chính bạn.
- Authorize lại (terminal): `python3 ~/.hermes/skills/doc-convert/scripts/authorize_google.py --port 8765` (VPS headless: SSH tunnel `ssh -L 8765:localhost:8765 <user>@<vps>`).
- Thư mục creds: skill chat giữ một symlink ở đường mặc định `skills/doc-convert/state/google-creds` trỏ tới thư mục thật, để `google_io` tìm thấy token kể cả khi gateway không export `DOC_CONVERT_GCREDS_DIR` vào tiến trình tool. `preflight.py` in `google.creds_dir` để đối chiếu.
- Cần enable Google Cloud Console: **Drive API + Docs API + Slides API**. Consent Testing → tài khoản phải nằm trong Test users.
- Kiểm tra: `python3 ~/.hermes/skills/doc-convert/scripts/preflight.py --compact` → `google.authorized_token: true`.
- **Hai bộ quyền** (`DOC_CONVERT_GOOGLE_SCOPES`) — scope quyết định khách setup dễ hay khó:
  - `minimal` — chỉ `drive.file`. Đủ cho toàn bộ pipeline (upload, export, đọc lại deck) vì mọi file đều do app tạo. Đây là scope **không nhạy cảm**: OAuth client chỉ xin chừng này thì publish không cần verification, không hiện màn hình "unverified app", và refresh token **không chết sau 7 ngày**. Khách setup = 1 cú bấm đồng ý. Đổi lại: link Google riêng tư bị từ chối kèm hướng dẫn tải file lên.
  - `private-links` (mặc định) — thêm `drive.readonly` để đọc link Docs/Slides/Drive riêng tư. Scope **RESTRICTED**: muốn publish phải qua verification + đánh giá CASA hằng năm, nên thực tế mỗi khách phải tự tạo OAuth client riêng.
  - Đã bỏ `documents` và `presentations` — code không còn dựng nội dung qua batchUpdate, phần đọc lại deck chạy được dưới `drive.file`.
  - `preflight.py` báo `scope_set_requested`, `granted_scopes`, `can_read_private_links`. Quyền ghi trong token thắng cấu hình trong code, nên bản đang chạy không gãy khi đổi mặc định.
- Khả năng: đọc Docs/Slides/Drive riêng tư (chỉ với `private-links`); mọi conversion đều được dựng trên Google.
- **Google là renderer chính thức.** `convert.py` dựng .pptx/.docx ở local, import vào Slides/Docs, rồi export ra đúng định dạng người dùng cần — deck do python-pptx tạo hiển thị lệch trong PowerPoint trên Mac, bản Google thì không. File tạo ra nằm ở chế độ riêng tư trong Drive của tài khoản đã kết nối; bản trung gian đã upload nằm trong `build/` của run dir.
- Target: `gslides`/`gdoc` (link + PDF export), `pptx`/`docx`/`pdf` (bản export của Google), `md` (local, không qua Google). `--no-google` ép render local để debug.
- Không có token thì vẫn convert được nhưng manifest thêm cảnh báo `google_unauthorized:rendered_locally` và `gslides`/`gdoc` fail — user báo file "hiển thị sai trên Mac" thì kiểm tra preflight trước.
- Kiểm tra sau import: `convert.py` đọc lại deck qua Slides API (`google_check` trong manifest); chạy lại bằng `validate_output.py --google <url>`.
- Drive từ chối export file trên **10 MB**: deck nhiều ảnh sẽ chỉ có link kèm cảnh báo `google_export_failed:`, không có PDF.

## Known limitations

- **TTS keyless**: dùng endpoint Google Translate không chính thức, có thể bị chặn/đổi. Nâng cấp: Google Cloud TTS (có key) hoặc `edge-tts`.
- **Ảnh minh họa slide (D2)**: phụ thuộc search provider; nếu search giới hạn thì slide có thể thiếu ảnh.
- **OAuth client secret đi qua chat**: đường cài đặt qua chat có nhận `client_secret` (hoặc cả file JSON) dán trong Telegram, nên bí mật đó nằm lại trong lịch sử chat của khách. Đây là đánh đổi có chủ đích để khách tự làm được. Sau khi kết nối xong, nên bảo khách **xoá tin nhắn đó**; muốn chặt chẽ hơn thì tạo client mới trong Google Cloud Console và xoá client cũ (`token.json` hiện tại vẫn dùng được cho tới khi client bị xoá). Khách không chấp nhận rủi ro này thì dùng đường terminal (bước 06).
