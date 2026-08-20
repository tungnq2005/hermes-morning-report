# Cài đặt lần đầu — làm hết trong chat

Dành cho **bạn, người dùng cuối**. Không cần biết gì về server, không cần cài phần mềm,
không cần ai giúp. Bạn chỉ cần điện thoại hoặc máy tính có Telegram và trình duyệt.

Tổng thời gian: **10 phút** nếu chỉ dùng bản tin sáng, **20 phút** nếu dùng cả chuyển đổi
tài liệu.

---

## Bắt đầu

Mở Telegram, tìm bot **@your_bot**, bấm **Start**, rồi nhắn:

> **Cài đặt giúp tôi**

Bot sẽ kiểm tra xem còn thiếu gì và dẫn bạn **từng bước một**. Cứ làm theo, mỗi lần một
việc. Bí chỗ nào thì nhắn thẳng cho bot — ví dụ *"mình không thấy nút đó"* — bot sẽ chỉ lại.

Muốn dừng giữa chừng cũng được: những gì đã kết nối vẫn giữ nguyên. Lúc nào rảnh nhắn
*"tiếp tục cài đặt"* là chạy tiếp từ chỗ dở.

---

## Bot sẽ xin bạn những gì

### 1. Chìa khoá tìm tin (cho bản tin sáng)

| Dịch vụ | Để làm gì | Bắt buộc? |
| --- | --- | --- |
| **Exa** | tìm tin trong 24h qua theo chủ đề của bạn | **Có** — không có thì bản tin không chạy |
| **Firecrawl** | đọc trọn nội dung bài báo, không chỉ tiêu đề | Nên có |
| **Brave Search** | tìm tin dự phòng khi Exa lỗi hoặc hết lượt | Tuỳ chọn |

Cả ba đều **có gói miễn phí**. Với mỗi cái, bot gửi bạn một đường link, chỉ bạn bấm vào
đâu để tạo "API key", rồi bạn **copy dán vào chat**. Bot kiểm tra ngay với nhà cung cấp và
báo lại là dùng được hay chưa.

> "API key" chỉ là một dòng chữ dài, kiểu mật khẩu riêng cho ứng dụng. Bạn không cần hiểu
> nó là gì — chỉ cần copy đúng dòng đó.

### 2. Chủ đề và giờ gửi bản tin

Bot hỏi bằng lời: bạn muốn theo dõi chủ đề gì, gửi lúc mấy giờ, ngôn ngữ nào, phong cách
ngắn gọn hay phân tích sâu, có kèm audio không. Trả lời tự nhiên là được. Bot tóm tắt lại
và chỉ lưu khi bạn xác nhận.

### 3. Kết nối Google (nếu bạn muốn dùng chuyển đổi tài liệu)

Để file bot tạo ra mở trên Mac, Windows hay iPad đều hiển thị giống nhau, bot dựng
slide/tài liệu **trong Google Drive của chính bạn**. Việc này cần bạn cho phép một lần.

Bạn sẽ làm hai việc:

1. Tạo một "ứng dụng" trên trang quản trị của Google (bot chỉ từng nút bấm, khoảng 8 phút,
   miễn phí) rồi gửi lại cho bot phần thông tin nó cần.
2. Bấm vào link bot gửi → chọn tài khoản Google của bạn → bấm **Cho phép**.

**Đọc kỹ chỗ này:** sau khi bấm Cho phép, trình duyệt sẽ nhảy sang một trang **báo lỗi
không mở được** (*"This site can't be reached"* / *"Không thể truy cập trang web này"*).
**Đúng như vậy mới là thành công.** Bạn chỉ cần **copy toàn bộ đường link trên thanh địa
chỉ** của trang lỗi đó và dán vào chat. Bot lo phần còn lại.

Xong, bot chạy thử một file thật và gửi bạn link để kiểm chứng.

Kết nối Google xong còn được thêm một thứ: **bản tin sáng biến thành tài liệu** chỉ bằng
một câu nhắn — *"Xuất bản tin sáng nay ra Google Docs"* hay *"Làm slide từ bản tin hôm
qua"*, không cần gửi lại file nào.

---

## Những điều bạn nên biết

- **Bot không bao giờ thấy mật khẩu Google của bạn.** Bạn đăng nhập trên trang của Google,
  bot chỉ nhận được quyền tạo file.
- **File bot tạo nằm riêng tư trong Drive của bạn.** Người khác không mở được, trừ khi bạn
  tự chia sẻ.
- **Bot chỉ đụng được file do chính nó tạo** (trừ khi bạn chọn cho phép đọc link riêng tư
  — bot sẽ hỏi trước và giải thích).
- **Thu hồi lúc nào cũng được**: vào <https://myaccount.google.com/permissions>, chọn ứng
  dụng, bấm *Remove access*.
- **Đừng gửi mật khẩu hay số thẻ cho bot.** Không có bước nào cần đến chúng. Nếu ai đó bảo
  bạn làm vậy, đó không phải quy trình này.

---

## Khi có trục trặc

| Bạn thấy | Nhắn cho bot |
| --- | --- |
| Không biết đang thiếu gì | *"Kiểm tra cài đặt giúp tôi"* |
| Bot báo key không dùng được | *"Mình tạo key mới, đổi giúp mình"* |
| Bản tin sáng không đến | *"Chạy thử morning report ngay"* |
| Bot bảo chưa kết nối Google | *"Kết nối Google giúp tôi"* |
| Bot không đọc được link Google riêng tư bạn dán | *"Kết nối lại Google, cho phép đọc link riêng tư"* |
| Muốn đổi sang tài khoản Google khác | *"Kết nối lại Google bằng tài khoản khác"* |

Bot không trả lời sau 2 phút? Báo người quản trị hệ thống — lúc đó là chuyện của server,
không phải của bạn.

---

Bản tiếng Anh: [first-run-setup.en.md](first-run-setup.en.md) ·
Cách dùng hằng ngày: [user-guide.vi.md](user-guide.vi.md) ·
Bảng lệnh nhanh: [chat-commands.md](chat-commands.md)
