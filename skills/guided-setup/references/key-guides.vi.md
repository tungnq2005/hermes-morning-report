# Hướng dẫn lấy key — bản tiếng Việt (dùng để nhắn cho người dùng)

Tài liệu này dành cho **trợ lý**, không phải để gửi nguyên văn. Mỗi mục có sẵn các bước
ngắn để nhắn lại từng tin một. Quy tắc: **mỗi lần một dịch vụ**, gửi link trên dòng
riêng, hỏi xong thì dừng lại chờ người dùng dán key.

Nếu người dùng mô tả màn hình khác với mô tả ở đây (nhà cung cấp hay đổi giao diện),
đừng đoán: hỏi họ đang thấy nút/chữ gì rồi dẫn theo đó.

---

## Exa — tìm tin (bắt buộc cho Bản tin sáng)

**Nói trước:** đây là dịch vụ tìm tin trong 24h qua cho bản tin. Có gói miễn phí, không
cần thẻ để bắt đầu.

Các bước nhắn cho người dùng:

1. Mở link này: https://dashboard.exa.ai/api-keys
2. Đăng nhập bằng Google (hoặc email) — lần đầu thì bấm đăng ký.
3. Bấm nút tạo key mới (**Create API Key**), đặt tên gì cũng được, ví dụ `hermes`.
4. Bấm biểu tượng copy để sao chép key.
5. Dán key vào đây cho mình.

**Key trông như thế nào:** một chuỗi dài có dấu gạch ngang, kiểu
`a1b2c3d4-e5f6-7890-abcd-ef1234567890`. Không phải địa chỉ web, không phải email.

**Lưu ý thường gặp:** key chỉ hiện đầy đủ lúc mới tạo. Nếu người dùng đã đóng cửa sổ và
không copy kịp, bảo họ tạo key mới — nhanh hơn đi tìm.

Lưu bằng: `save_key.py --name exa --value "<đoạn người dùng dán>"`

---

## Firecrawl — đọc nội dung bài báo (nên có)

**Nói trước:** giúp bot đọc được đầy đủ nội dung bài báo thay vì chỉ tiêu đề. Không có
cũng chạy được, chỉ là bản tin sẽ mỏng hơn với vài trang báo. Gói miễn phí có sẵn.

Các bước nhắn cho người dùng:

1. Mở link này: https://www.firecrawl.dev/app/api-keys
2. Đăng nhập/đăng ký (đăng nhập bằng Google là nhanh nhất).
3. Ở mục **API Keys**, copy key có sẵn, hoặc bấm tạo key mới rồi copy.
4. Dán vào đây cho mình.

**Key trông như thế nào:** bắt đầu bằng `fc-`, ví dụ `fc-1a2b3c4d...`.

Lưu bằng: `save_key.py --name firecrawl --value "<đoạn người dùng dán>"`

---

## Brave Search — tìm tin dự phòng (tuỳ chọn)

**Nói trước:** chỉ dùng khi Exa bị lỗi hoặc hết lượt, để bản tin sáng không bị trống.
Bỏ qua được, cài sau lúc nào cũng được.

Các bước nhắn cho người dùng:

1. Mở link này: https://api-dashboard.search.brave.com/app/keys
2. Đăng ký/đăng nhập tài khoản Brave.
3. Chọn gói **Free** trong mục Subscriptions. Brave có thể yêu cầu nhập thẻ để xác minh
   dù gói miễn phí — nếu người dùng không muốn, **bỏ qua dịch vụ này**, mọi thứ khác vẫn
   chạy bình thường.
4. Vào mục **API Keys** → tạo key → copy.
5. Dán vào đây cho mình.

**Key trông như thế nào:** thường bắt đầu bằng `BSA`, ví dụ `BSAxxxxxxxxxxxxxxxx`.

Lưu bằng: `save_key.py --name brave --value "<đoạn người dùng dán>"`

---

## Google — xuất kết quả ra Google Slides/Docs (tuỳ chọn, cho Chuyển đổi tài liệu)

Đây là phần dài nhất: khoảng 10 phút bấm trên trình duyệt và **2 lần dán vào chat**.
Lý do đầy đủ cho từng màn hình nằm ở `docs/google-oauth-setup.vi.md`.

**Nói trước:** bot sẽ dựng slide/tài liệu **trên Google Drive của chính người dùng**, để
mở trên Mac, Windows hay iPad đều hiển thị giống nhau. File nằm ở chế độ riêng tư trong
Drive của họ; bot không đọc được gì khác và không bao giờ thấy mật khẩu Google.

**Hỏi trước một lần:** người dùng có hay dán link Google Docs/Slides *riêng tư* vào chat
và muốn bot đọc trực tiếp không?
- **Không** (mặc định) → dùng bộ quyền `minimal`: bot chỉ đụng file do chính nó tạo,
  và **không hiện màn hình cảnh báo** nào.
- **Có** → `private-links`: bot đọc được file người dùng có quyền xem, nhưng lúc cấp
  quyền sẽ gặp màn hình *"Google hasn't verified this app"* phải bấm qua.

### G1. Tạo dự án trên Google Cloud

1. Mở link này bằng **đúng tài khoản Google mà bạn muốn file được lưu vào**:
   https://console.cloud.google.com/
2. Ở thanh trên cùng, bấm ô chọn dự án → **New Project** (Dự án mới).
3. Đặt tên bất kỳ, ví dụ `tro-ly-tai-lieu` → **Create**.
4. Đợi vài giây, rồi chọn đúng dự án vừa tạo ở ô trên cùng.

### G2. Bật quyền dùng Google Drive

1. Vào **APIs & Services → Library** (Thư viện).
2. Gõ tìm `Google Drive API` → mở ra → bấm **Enable**.
3. Tìm tiếp `Google Slides API` → **Enable**. (Không bật cũng chạy, nhưng bot sẽ không tự
   kiểm tra được slide sau khi tạo.)

### G3. Khai báo ứng dụng — và **PUBLISH**

1. Vào **APIs & Services → OAuth consent screen** (bản mới hiển thị là **Google Auth
   Platform**).
2. Chọn **External** → **Create**.
3. Điền: tên ứng dụng (ví dụ `Tro ly tai lieu`), email hỗ trợ, email liên hệ. Không cần
   logo, không cần gì thêm. Bấm lưu qua hết các bước.
4. **Quan trọng nhất:** tìm mục **Publishing status** (bản mới: **Audience**) → bấm
   **PUBLISH APP** → xác nhận. Trạng thái phải chuyển thành **In production**.

> Nói rõ cho người dùng vì sao bước 4 bắt buộc: để nguyên **Testing**, Google chỉ cho kết
> nối sống **đúng 7 ngày**, sau đó bot đứt kết nối mà không ai hiểu vì sao. Publish
> **không** làm ứng dụng hiện ra công khai cho người lạ — nó chỉ là trạng thái phát hành.

### G4. Tạo OAuth client — nhớ chọn **Desktop app**

1. Vào **APIs & Services → Credentials**.
2. **Create credentials → OAuth client ID**.
3. Application type: chọn **Desktop app** ← đúng loại này. Chọn *Web application* sẽ hỏng
   ở bước cuối.
4. Đặt tên bất kỳ → **Create**.
5. Bấm **Download JSON** (hoặc để nguyên màn hình đang hiện **Client ID** và
   **Client secret**).
6. Gửi cho mình theo **một trong hai cách**:
   - gửi thẳng file JSON vừa tải vào chat này, **hoặc**
   - copy **Client ID** và **Client secret** trên màn hình rồi dán vào đây.

Lưu bằng: `google_setup.py client --file <đường dẫn file>` · `--json "<nội dung dán>"` ·
hoặc `--client-id ... --client-secret ...` (thêm `--scopes private-links` nếu người dùng
chọn đọc link riêng tư).

### G5. Bấm Cho phép một lần

Chạy `google_setup.py start`, gửi `auth_url` **trên một dòng riêng**, rồi nhắn đúng thứ
tự này:

1. Mở link, chọn **đúng tài khoản Google** vừa dùng ở bước trên.
2. (Chỉ với `private-links`) Nếu hiện *"Google hasn't verified this app"* → bấm
   **Advanced** → **Go to … (unsafe)**. Đây là chuyện bình thường với ứng dụng riêng.
3. Bấm **Continue / Cho phép**.
4. Trình duyệt sẽ nhảy sang một trang **báo lỗi không mở được** (kiểu *"This site can't
   be reached"* / *"Không thể truy cập trang web này"*). **Đúng như vậy là thành công** —
   phải nói trước câu này, nếu không người dùng sẽ tưởng hỏng.
5. Copy **toàn bộ đường link trên thanh địa chỉ** của trang lỗi đó rồi dán vào đây.

Hoàn tất bằng: `google_setup.py finish --redirect-url "<đoạn người dùng dán>"`

### G6. Kiểm chứng

Chạy `google_setup.py test`, gửi `google_url` dạng link bấm được và nói: file này nằm
riêng tư trong Drive của họ, xoá lúc nào cũng được.

---

## Khi người dùng dán nhầm

`save_key.py` tự nhận diện các trường hợp dưới đây và trả về trong `problems`. Nhắn lại
bằng lời, đừng đọc mã lỗi cho người dùng:

| `problems` | Nói với người dùng |
| --- | --- |
| `looks_like_url` | "Cái này là địa chỉ trang web. Key là dòng chữ **nằm trong** trang đó nhé." |
| `looks_like_email` | "Đây là email đăng nhập, không phải key." |
| `contains_spaces` | "Hình như copy dư cả câu chữ xung quanh — bạn copy đúng dòng key thôi giúp mình." |
| `placeholder` | "Đây là chữ mẫu trên màn hình, chưa phải key thật." |
| `too_short` | "Key bị thiếu mất một đoạn — bạn copy lại toàn bộ dòng giúp mình." |
| `verify.state: rejected` | "Nhà cung cấp báo key này không dùng được. Bạn tạo key mới rồi gửi lại giúp mình nhé." |
