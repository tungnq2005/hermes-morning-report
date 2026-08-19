# Hướng dẫn sử dụng — Trợ lý AI qua Telegram

Trợ lý của bạn hoạt động hoàn toàn qua **chat Telegram** với bot. Bạn không cần đụng đến server, code hay cài đặt gì cả — chỉ cần nhắn tin bằng tiếng Việt tự nhiên.

Bot: **@your_bot** (mở Telegram, tìm tên này, bấm Start).

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
- **Đầu ra**: **Google Slides / Google Docs** (mặc định), kèm PowerPoint, Word, PDF, Markdown, hoặc audio MP3.

### Cách dùng
- **Word → slide**: gửi file .docx kèm *"Chuyển file này thành PowerPoint"* → nhận **link Google Slides** kèm bản PDF
- **→ PDF**: *"Xuất file này ra PDF"*
- **PowerPoint → tài liệu**: gửi .pptx kèm *"Chuyển slide này thành tài liệu Word"*
- **Từ link Google**: dán link kèm *"Chuyển tài liệu này thành slide"* (đọc được cả file **riêng tư** trong tài khoản Google đã kết nối)
- **Vẫn muốn file Office?** Nhắn thêm: *"Gửi mình cả file .pptx"*
- **Tường thuật thành audio**: gửi file kèm *"Đọc tài liệu này thành audio"*

Bot trả về link Google kèm file PDF đính kèm ngay trong chat. Thời gian xử lý thường **5–10 phút** tùy độ dài.

### Vì sao dùng Google Slides / Google Docs?
File PowerPoint tạo trên server không phải lúc nào cũng hiển thị giống nhau khi mở bằng PowerPoint trên máy Mac — font, khoảng cách và bố cục bị lệch. Google dựng bản trình bày một lần, nên nội dung hiển thị y hệt trên macOS, Windows, iPad và trình duyệt; mọi file .pptx/.docx/.pdf bạn cần đều được xuất ra từ chính file Google đó.

### Lưu ý
- File bot tạo nằm trong **Google Drive của chính bạn và ở chế độ riêng tư** — người khác không mở được link. Muốn chia sẻ thì bạn tự chia sẻ.
- File Google riêng tư **đã đọc được** qua tài khoản đã kết nối. File của người khác chia sẻ cho bạn cũng đọc được nếu tài khoản đó có quyền.
- PDF dạng ảnh scan (không có chữ) không xử lý được.
- Chỉnh sửa/tạo video: **ngoài phạm vi** (sẽ là tính năng riêng sau này).

---

## Khi gặp sự cố
- Bot không trả lời? Đợi 1–2 phút (bot có thể đang bận xử lý). Nếu vẫn im, báo người quản trị.
- Không nhận được bản tin sáng? Kiểm tra bạn chưa "tạm dừng"; nhắn *"Chạy thử morning report ngay"* để kiểm tra.
- Câu hỏi khác? Cứ nhắn bot bằng tiếng Việt bình thường — nó hiểu ngôn ngữ tự nhiên.
