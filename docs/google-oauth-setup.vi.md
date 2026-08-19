# Kết nối Google Workspace cho Document Conversion

Tài liệu này dành cho **người cài đặt** (bạn hoặc kỹ thuật viên của khách). Người dùng
cuối không cần đọc — họ chỉ bấm "Cho phép" đúng một lần ở Bước 7.

Làm đủ các bước mất khoảng **15 phút**. Có **một bước ai cũng bỏ qua và nó làm bot chết
đúng 7 ngày sau** — Bước 5. Đừng bỏ.

---

## 1. Vì sao cần bước này

Bot dựng kết quả trên Google rồi mới giao cho người dùng: file .pptx do server tạo hiển
thị khác nhau giữa PowerPoint trên Windows và trên máy Mac (font, khoảng cách, bố cục),
trong khi một file Google Slides hiển thị **y hệt** trên macOS, Windows, iPad và trình
duyệt. Mọi file .pptx/.docx/.pdf trả về cho người dùng đều được **xuất ra từ chính file
Google đó**, nên kết quả không còn phụ thuộc vào máy người xem.

Để làm được vậy, bot cần quyền tạo file trong Google Drive **của người dùng**. Quyền đó
lấy qua OAuth — đúng cơ chế "Đăng nhập bằng Google" quen thuộc.

Không kết nối Google thì bot **vẫn chạy**: nó dựng file bằng thư viện cục bộ và ghi cảnh
báo `google_unauthorized:rendered_locally` trong manifest. Nhưng đó chính là loại file
hiển thị lệch trên máy Mac, và hai lệnh `--to gslides` / `--to gdoc` sẽ báo lỗi.

---

## 2. Chọn bộ quyền trước khi bắt đầu

Đây là quyết định quan trọng nhất: nó đổi cả cách cài lẫn trải nghiệm người dùng.

| | `minimal` | `private-links` (mặc định) |
| --- | --- | --- |
| Quyền xin | `drive.file` | `drive.file` + `drive.readonly` |
| Bot thấy gì trong Drive | **Chỉ file do chính bot tạo** | Mọi file người dùng có quyền xem |
| Đọc link Google Docs/Slides riêng tư người dùng dán vào | Không | Có |
| Google xếp loại | Không nhạy cảm | **Restricted** |
| Màn hình "Google hasn't verified this app" | Không hiện | Có, phải bấm Advanced → Continue |
| Muốn phát hành rộng | Không cần thẩm định | Cần app verification + đánh giá CASA hằng năm |
| Refresh token hết hạn sau 7 ngày? | Không, **nếu** đã làm Bước 5 | Không, **nếu** đã làm Bước 5 |

**Chọn `minimal`** nếu người dùng chủ yếu gửi file thẳng vào Telegram. Gọn nhất: không
màn hình cảnh báo, quyền hẹp nhất, và dễ giải thích với khách — "bot chỉ đụng được file
do chính nó tạo, không đọc được gì khác trong Drive của bạn".

**Chọn `private-links`** nếu người dùng hay dán link Google Docs/Slides riêng tư vào chat
và muốn bot đọc trực tiếp.

Đặt bộ quyền bằng biến môi trường trên server:

```bash
# trong ~/.hermes/.env  (hoặc export trước khi chạy authorize)
DOC_CONVERT_GOOGLE_SCOPES=minimal        # hoặc: private-links
```

Đổi bộ quyền **sau khi đã authorize** thì phải authorize lại — quyền ghi trong token mới
là quyền thật, không phải giá trị trong biến môi trường.

---

## 3. Tạo project trên Google Cloud

1. Mở <https://console.cloud.google.com/> bằng **đúng tài khoản Google mà khách muốn file
   được tạo vào Drive của nó**. Chọn nhầm tài khoản là mọi file sau này nằm sai chỗ.
2. Góc trên bên trái, bấm ô chọn project → **New Project**.
3. Đặt tên dễ nhận (ví dụ `hermes-doc-convert`) → **Create**.
4. Đợi vài giây rồi chọn đúng project vừa tạo. Kiểm tra lại tên trên thanh trên cùng —
   thao tác nhầm project là lỗi phổ biến nhất ở các bước sau.

---

## 4. Bật API cần dùng

Vào **APIs & Services → Library**, tìm và bật:

| API | Bắt buộc? | Dùng để làm gì |
| --- | --- | --- |
| **Google Drive API** | **Có** | Upload file, chuyển thành Google Slides/Docs, xuất ngược ra PDF/pptx/docx |
| **Google Slides API** | Nên bật | Đọc lại deck sau khi import để kiểm tra bố cục và độ tương phản chữ |
| Google Docs API | Không | Bot không gọi API này — nội dung đi bằng đường import, không dựng qua batchUpdate |

Không bật Slides API thì conversion vẫn chạy, chỉ có bước kiểm tra tự động báo
`google_check.status: "unchecked"` — nghĩa là **chưa kiểm tra được**, không phải "đạt".

---

## 5. Cấu hình màn hình xin quyền — và PUBLISH

Vào **APIs & Services → OAuth consent screen**.

1. User type: chọn **External** → **Create**.
   (*Internal* chỉ dùng được khi khách có Google Workspace doanh nghiệp và chỉ người trong
   tổ chức đó dùng. Tài khoản Gmail thường thì luôn là External.)
2. Điền tối thiểu: **App name** (ví dụ "Hermes Document Assistant"), **User support
   email**, **Developer contact email**. Không cần logo, không cần xác minh tên miền.
3. Lưu qua các bước cho tới khi quay về màn hình tổng quan.
4. Nhìn mục **Publishing status**. Nếu đang là **Testing** → bấm **PUBLISH APP** → xác
   nhận. Trạng thái phải chuyển thành **In production**.

> ### Vì sao mục 4 là bắt buộc
>
> Khi app còn ở chế độ **Testing**, Google cho refresh token sống **đúng 7 ngày**. Bot
> chạy ngon lành cả tuần rồi đột ngột hỏng, log báo `invalid_grant`, và không ai hiểu vì
> sao — "có sửa gì đâu". Publish sang Production là hết hẳn chuyện này.
>
> Publish **không** có nghĩa là app hiện công khai cho người lạ. Nó chỉ là trạng thái phát
> hành. App chưa thẩm định vẫn giới hạn 100 người dùng, và với bộ quyền `private-links`
> vẫn hiện màn hình cảnh báo khi đăng nhập.

---

## 6. Tạo OAuth client và tải file JSON

Vào **APIs & Services → Credentials**.

1. **Create credentials → OAuth client ID**.
2. Application type: **Desktop app** ← đúng loại này. Chọn *Web application* sẽ bắt khai
   báo redirect URI và làm hỏng luồng đăng nhập qua terminal.
3. Đặt tên bất kỳ → **Create**.
4. Bấm **Download JSON**. Giữ file cẩn thận: đây là bí mật của app.

> Google chỉ cho tải JSON của client **vừa tạo**. Nếu sau này làm mất, đừng mất công tìm
> cách tải lại — tạo một Desktop client mới (1 phút) rồi authorize lại.

---

## 7. Đưa lên server và cấp quyền một lần

Chép file JSON lên server, đặt đúng tên `client_secret.json`:

```bash
# chạy ở máy bạn
scp ~/Downloads/client_secret_*.json <user>@<vps>:~/hermes-google-creds/client_secret.json
```

Trên server, tạo thư mục và siết quyền:

```bash
mkdir -p ~/hermes-google-creds && chmod 700 ~/hermes-google-creds
chmod 600 ~/hermes-google-creds/client_secret.json
```

Cho skill biết thư mục đó — thêm vào `~/.hermes/.env`:

```bash
DOC_CONVERT_GCREDS_DIR=/home/<user>/hermes-google-creds
DOC_CONVERT_GOOGLE_SCOPES=minimal          # hoặc private-links
```

> Có thể bỏ biến `DOC_CONVERT_GCREDS_DIR` và đặt file vào đường dẫn mặc định
> `skills/doc-convert/state/google-creds/`. Nhưng để creds **ngoài** repo an toàn hơn:
> repo có thể bị copy, đóng gói hay commit nhầm. Nếu repo nằm trên ổ Windows chia sẻ vào
> WSL (`/mnt/c/...`) thì bắt buộc để ngoài, vì `chmod 600` không có tác dụng ở đó.

Chạy cấp quyền — **đúng một lần cho cả vòng đời cài đặt**:

```bash
cd <thư mục repo>
python3 skills/doc-convert/scripts/authorize_google.py --port 8765
```

Lệnh in ra bộ quyền đang xin kèm một URL. VPS không có trình duyệt, nên mở SSH tunnel từ
máy bạn để trình duyệt máy bạn nói chuyện được với cổng 8765 trên server:

```bash
# chạy ở máy bạn, giữ phiên này mở trong lúc bấm consent
ssh -L 8765:localhost:8765 <user>@<vps>
```

Rồi dán URL vào trình duyệt:

1. Chọn **đúng tài khoản Google** đã dùng ở Bước 3.
2. Nếu hiện *"Google hasn't verified this app"* → **Advanced** → *Go to … (unsafe)*.
   Bình thường với app chưa thẩm định; bộ quyền `minimal` không gặp màn hình này.
3. Xem danh sách quyền rồi bấm **Continue / Cho phép**.
4. Trình duyệt hiện "Xong! Có thể đóng tab này…" là thành công. Terminal in ra đường dẫn
   `token.json` vừa lưu (quyền 600).

---

## 8. Kiểm tra

```bash
python3 skills/doc-convert/scripts/preflight.py --compact | python3 -m json.tool
```

Phần `google` phải như sau:

```json
"google": {
  "libs_installed": true,
  "client_secret": true,
  "authorized_token": true,
  "scope_set_requested": "minimal",
  "granted_scopes": ["https://www.googleapis.com/auth/drive.file"],
  "can_read_private_links": false
}
```

`granted_scopes` đọc từ **token thật**, không phải từ cấu hình — đây mới là quyền bot
đang có. `can_read_private_links: false` với bộ `minimal` là đúng, không phải lỗi.

Chạy thử một lần chuyển đổi thật:

```bash
python3 skills/doc-convert/scripts/convert.py \
  --input docs/user-guide.vi.md --to gslides --no-auto-images --outdir /tmp/thu-nghiem
```

Trong JSON kết quả cần thấy:

- `"success": true`
- `"render_engine": "google"` — file do Google dựng, không phải thư viện cục bộ
- `"google_url"` — mở được bằng trình duyệt, nằm trong Drive của khách ở chế độ riêng tư
- `"google_check": {"status": "pass"}` — deck sau khi import đã được đọc lại và kiểm tra
- `"output"` — đường dẫn file PDF do Google xuất

Mở `google_url` xem một lượt. Đây cũng là lúc tốt nhất để khách xác nhận file nằm đúng
tài khoản Drive mà họ muốn.

---

## 9. Bảo mật và quyền riêng tư — trả lời khách

- **Bot đọc được gì trong Drive của tôi?** Với `minimal`: chỉ file do chính bot tạo. Nó
  không liệt kê, không mở, không xoá được bất kỳ file nào khác. Với `private-links`: đọc
  được file bạn có quyền xem, nhưng chỉ khi bạn chủ động dán link.
- **File bot tạo ai xem được?** Chỉ bạn. File nằm trong Drive của bạn ở chế độ riêng tư;
  bot không đổi chế độ chia sẻ. Muốn chia sẻ thì bạn tự chia sẻ như file thường.
- **Ai giữ mật khẩu Google của tôi?** Không ai. Bot không bao giờ thấy mật khẩu; nó chỉ
  giữ một refresh token do Google cấp, và bạn thu hồi được bất cứ lúc nào.
- **Thu hồi thế nào?** <https://myaccount.google.com/permissions> → chọn app → **Remove
  access**. Bot báo lỗi ngay lần chạy kế tiếp cho tới khi authorize lại.
- **File nhạy cảm nằm ở đâu trên server?** `client_secret.json` và `token.json`, quyền
  600, trong thư mục `DOC_CONVERT_GCREDS_DIR` (quyền 700). `.gitignore` đã loại trừ
  `**/google-creds/`, `token.json`, `client_secret.json` — nhưng vẫn nên để creds ngoài repo.

---

## 10. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chạy được vài ngày rồi hỏng, log `invalid_grant` | App còn ở chế độ **Testing** → token hết hạn sau 7 ngày | Publish app (Bước 5) rồi chạy lại `authorize_google.py` |
| `Chưa authorize Google. Chạy 1 lần: …` | Thiếu `token.json`, hoặc sai `DOC_CONVERT_GCREDS_DIR` | Kiểm tra bằng preflight, rồi authorize lại |
| `THIẾU …/client_secret.json` | Chưa chép file JSON lên, hoặc đặt sai tên | Đổi tên đúng thành `client_secret.json` |
| Trình duyệt báo `redirect_uri_mismatch` | Tạo nhầm client loại **Web application** | Tạo lại client loại **Desktop app** |
| Trình duyệt quay mãi rồi lỗi kết nối `127.0.0.1:8765` | Chưa mở SSH tunnel, hoặc cổng đã bị chiếm | Mở tunnel; hoặc đổi `--port 8766` và sửa lệnh tunnel theo |
| `access_denied` | Bấm nhầm "Cancel", hoặc app Testing mà tài khoản không nằm trong Test users | Publish app, hoặc thêm tài khoản vào Test users |
| Bot báo *"chỉ có quyền với file do bot tạo, không đọc được link Google riêng tư"* | Đang dùng bộ `minimal` | Tải file lên trực tiếp, hoặc authorize lại với `private-links` |
| `google_check.status: "unchecked"` | Chưa bật **Google Slides API** | Bật API rồi chạy lại; deck vẫn dùng được bình thường |
| Có link nhưng không kèm PDF, cảnh báo `google_export_failed` | Drive từ chối xuất file trên **10 MB** | Bình thường với deck nhiều ảnh — giao link là đủ |
| `warnings: ["google_unauthorized:rendered_locally"]` | Không có token; file do thư viện cục bộ dựng | Hoàn tất Bước 7; file hiện tại có thể hiển thị lệch trên máy Mac |

---

## 11. Bảo trì

- **Không có việc định kỳ nào** nếu đã publish app: refresh token tự làm mới.
- **Đổi tài khoản Google**: xoá `token.json`, chạy lại `authorize_google.py`, đăng nhập
  tài khoản mới. File cũ vẫn nằm ở Drive tài khoản cũ.
- **Client secret bị lộ**: vào Credentials, xoá client cũ, tạo Desktop client mới, chép
  JSON mới lên server, authorize lại.
- **Đổi bộ quyền**: sửa `DOC_CONVERT_GOOGLE_SCOPES`, xoá `token.json`, authorize lại.
- **Dọn file thử nghiệm**: file bot tạo lúc test nằm trong Drive của khách như file thường
  — xoá tay được, hoặc để đó vì chúng riêng tư.

---

Bản tiếng Anh: [google-oauth-setup.en.md](google-oauth-setup.en.md) ·
Vận hành chung: [operator-runbook.vi.md](operator-runbook.vi.md)
