# Hướng dẫn sử dụng — Trợ lý AI qua Telegram

Trợ lý của bạn hoạt động hoàn toàn qua **chat Telegram** với bot. Bạn không cần đụng đến server, code hay cài đặt gì cả — chỉ cần nhắn tin bằng tiếng Việt tự nhiên.

Bot: **@tungnq_bot** (mở Telegram, tìm tên này, bấm Start).

Trợ lý có 2 khả năng chính:

---

## 1. Bản tin buổi sáng (Morning Report)

Mỗi sáng bot tự gửi cho bạn một bản tin tổng hợp về các chủ đề bạn quan tâm, gồm **bản chữ** + **file audio 3–5 phút** để nghe khi di chuyển.

### Cài đặt lần đầu
Nhắn:
> Setup Morning Report cho tôi

Bot sẽ hỏi lần lượt: chủ đề theo dõi, giờ gửi, múi giờ, phong cách (ngắn gọn / phân tích sâu / cơ hội & rủi ro), ngôn ngữ, có kèm audio không. Cứ trả lời tự nhiên. Cuối cùng bot **tóm tắt lại và chờ bạn xác nhận** — nhắn "OK" hoặc "đồng ý" thì mới lưu.

### Dùng hằng ngày
- **Xem thử ngay** (không đợi sáng mai): *"Chạy thử morning report ngay"*
- **Đổi chủ đề**: *"Đổi chủ đề sang chứng khoán và giá vàng"*
- **Thêm / bớt chủ đề**: *"Thêm chủ đề tin công nghệ"* / *"Bỏ chủ đề thời tiết"*
- **Đổi giờ gửi**: *"Đổi giờ gửi báo cáo sang 6h30 sáng"*
- **Đổi phong cách / ngôn ngữ**: *"Chuyển sang phong cách phân tích sâu"*
- **Tạm dừng**: *"Tạm dừng morning report"*
- **Bật lại**: *"Bật lại morning report"*
- **Xem cấu hình hiện tại**: *"Morning report đang cấu hình thế nào?"*

---

## 2. Chuyển đổi & tường thuật tài liệu (Document Conversion)

Gửi cho bot một **file** (kéo–thả vào chat) hoặc một **link Google công khai**, kèm yêu cầu.

### Các định dạng hỗ trợ
- **Đầu vào**: Word (.docx), PowerPoint (.pptx), PDF (dạng chữ), Text/Markdown, link Google Docs/Slides/Drive (đặt chế độ "Bất kỳ ai có link").
- **Đầu ra**: PowerPoint, Word, PDF, Markdown, hoặc audio MP3.

### Cách dùng
- **Word → PowerPoint**: gửi file .docx kèm *"Chuyển file này thành PowerPoint"*
- **→ PDF**: *"Xuất file này ra PDF"*
- **PowerPoint → Word**: gửi .pptx kèm *"Chuyển slide này thành tài liệu Word"*
- **Từ link Google**: dán link kèm *"Chuyển tài liệu này thành PowerPoint"* (đọc được cả file **riêng tư** trong tài khoản Google đã kết nối)
- **Tạo thẳng lên Google**: *"Tạo file này thành Google Docs"* / *"...thành Google Slides"* → bot trả về **link Google** mở sửa trực tiếp.
- **Tường thuật thành audio**: gửi file kèm *"Đọc tài liệu này thành audio"*

Bot trả về file kết quả đính kèm ngay trong chat (hoặc link Google nếu tạo trên cloud). Thời gian xử lý thường **5–10 phút** tùy độ dài.

### Lưu ý
- File Google riêng tư **đã đọc được** qua tài khoản đã kết nối. File của người khác chia sẻ cho bạn cũng đọc được nếu tài khoản đó có quyền.
- PDF dạng ảnh scan (không có chữ) không xử lý được.
- Chỉnh sửa/tạo video: **ngoài phạm vi** (sẽ là tính năng riêng sau này).

---

## Khi gặp sự cố
- Bot không trả lời? Đợi 1–2 phút (bot có thể đang bận xử lý). Nếu vẫn im, báo người quản trị.
- Không nhận được bản tin sáng? Kiểm tra bạn chưa "tạm dừng"; nhắn *"Chạy thử morning report ngay"* để kiểm tra.
- Câu hỏi khác? Cứ nhắn bot bằng tiếng Việt bình thường — nó hiểu ngôn ngữ tự nhiên.
