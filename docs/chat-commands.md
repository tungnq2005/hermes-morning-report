# Chat Command Quick Reference / Bảng lệnh nhanh

One page. Message **@your_bot** in natural language — these are examples, not exact syntax.
Một trang. Nhắn **@your_bot** bằng ngôn ngữ tự nhiên — đây là ví dụ, không phải cú pháp cứng.

---

## 🧭 Setup & keys / Cài đặt & chìa khoá

Everything here is done in chat — no server access needed.
Toàn bộ mục này làm trong chat — không cần đụng server.

| Action / Thao tác | Say something like / Nhắn đại loại |
|---|---|
| First-time setup / Cài đặt lần đầu | "Set up the assistant for me" · "Cài đặt giúp tôi" |
| Continue an unfinished setup / Cài tiếp | "Continue the setup" · "Tiếp tục cài đặt" |
| See what's missing / Xem còn thiếu gì | "Check my setup" · "Kiểm tra cài đặt giúp tôi" |
| Replace a key / Đổi key | "I made a new Exa key, replace it" · "Mình tạo key Exa mới, đổi giúp mình" |
| Connect Google / Kết nối Google | "Connect Google for me" · "Kết nối Google giúp tôi" |
| Allow private Google links / Cho đọc link riêng tư | "Reconnect Google with private link access" · "Kết nối lại Google, cho phép đọc link riêng tư" |
| Switch Google account / Đổi tài khoản Google | "Reconnect Google with another account" · "Kết nối lại Google bằng tài khoản khác" |

The bot sends one link at a time and tells you exactly what to copy. After pressing
**Allow** for Google, the browser shows an **error page — that is the expected result**;
copy the whole address from the address bar into the chat.
Bot gửi từng link một và chỉ rõ cần copy cái gì. Sau khi bấm **Cho phép** ở Google, trình
duyệt hiện **trang báo lỗi — đúng như vậy là thành công**; copy toàn bộ đường link trên
thanh địa chỉ rồi dán vào chat.

---

## 🌅 Morning Report / Bản tin sáng

| Action / Thao tác | Say something like / Nhắn đại loại |
|---|---|
| First setup / Cài lần đầu | "Set up Morning Report for me" · "Setup Morning Report cho tôi" |
| Preview now / Xem thử ngay | "Run the morning report now" · "Chạy thử morning report ngay" |
| Change topics / Đổi chủ đề | "Change topics to stocks and gold" · "Đổi chủ đề sang chứng khoán và giá vàng" |
| Add topic / Thêm chủ đề | "Add technology news" · "Thêm chủ đề tin công nghệ" |
| Remove topic / Bớt chủ đề | "Remove weather" · "Bỏ chủ đề thời tiết" |
| Change time / Đổi giờ | "Send it at 6:30 AM" · "Đổi giờ gửi sang 6h30" |
| Change timezone / Đổi múi giờ | "Use Asia/Ho_Chi_Minh timezone" · "Đổi múi giờ sang Asia/Ho_Chi_Minh" |
| Change style / Đổi phong cách | "Switch to deep analysis" · "Chuyển sang phân tích sâu" |
| Change language / Đổi ngôn ngữ | "Send the report in English" · "Gửi báo cáo bằng tiếng Anh" |
| Audio on/off / Bật-tắt audio | "Turn off the audio summary" · "Tắt audio summary" |
| Pause / Tạm dừng | "Pause the morning report" · "Tạm dừng morning report" |
| Resume / Bật lại | "Resume the morning report" · "Bật lại morning report" |
| View config / Xem cấu hình | "What's my morning report setup?" · "Morning report đang cấu hình thế nào?" |

Styles / Phong cách: **concise** (ngắn gọn) · **deep_analysis** (phân tích sâu) · **opportunities_risks** (cơ hội & rủi ro)

### 🔗 Turn a report into a document / Biến bản tin thành tài liệu

No need to send anything back — the bot still has the report.
Không cần gửi lại gì cả — bot vẫn giữ bản tin.

| Action / Thao tác | Say something like / Nhắn đại loại |
|---|---|
| Today's report as a doc / Bản tin hôm nay ra tài liệu | "Send today's report as a Google Doc" · "Xuất bản tin sáng nay ra Google Docs" |
| An older one / Bản tin cũ hơn | "The crypto report from yesterday as a Google Doc" · "Bản tin crypto hôm qua ra Google Docs" |
| As slides / Thành slide | "Make slides from this morning's report" · "Làm slide từ bản tin sáng nay" |
| As PDF | "Send that report as a PDF" · "Gửi bản tin đó dạng PDF" |
| Which ones exist / Có những bản tin nào | "What reports can you export?" · "Có những bản tin nào xuất được?" |
| Always save to Drive / Luôn lưu vào Drive | "Always save the gold report to Google Docs" · "Bản tin giá vàng thì lưu luôn vào Google Docs" |
| Stop saving / Thôi lưu | "Stop saving the gold report to Google Docs" · "Thôi lưu bản tin giá vàng vào Google Docs" |

Asking twice for the same report returns the **same file**, not a duplicate — say "make a
new one" if you really want a second copy. Needs Google connected.
Xuất lại lần hai trả về **đúng file cũ**, không tạo bản trùng — muốn bản mới thì nói "tạo
file mới giúp mình". Cần đã kết nối Google.

---

## 📄 Document Conversion / Chuyển đổi tài liệu

Attach a file or paste a public Google link, then add a request.
Đính kèm file hoặc dán link Google công khai, kèm yêu cầu.

| Action / Thao tác | Say something like / Nhắn đại loại |
|---|---|
| To slides / Sang slide | "Convert this to PowerPoint" · "Chuyển file này thành PowerPoint" → Google Slides + PDF |
| To a document / Sang tài liệu | "Turn these slides into a Word doc" · "Chuyển slide này thành Word" → Google Docs + PDF |
| To PDF / Sang PDF | "Export this as PDF" · "Xuất ra PDF" |
| To Markdown | "Convert this to Markdown" · "Chuyển thành Markdown" |
| Office file too / Kèm file Office | "Send me the .pptx file too" · "Gửi mình cả file .pptx" |
| Narrate audio / Đọc thành audio | "Read this document as audio" · "Đọc tài liệu này thành audio" |

**Also / Ngoài ra**: a Morning Report you already received counts as an input — just ask, no file needed (see 🔗 above) / một bản tin sáng bạn đã nhận cũng là đầu vào — chỉ cần nhắn, không phải gửi file (xem mục 🔗 ở trên).

**Input / Đầu vào**: .docx, .pptx, text-PDF, .txt, .md, Google Docs/Slides/Drive links (public **or private** in the connected account / công khai **hoặc riêng tư** trong tài khoản đã kết nối).
**Output / Đầu ra**: a **Google Slides/Docs link + PDF** by default; PowerPoint, Word, Markdown or MP3 on request / mặc định là **link Google Slides/Docs + PDF**; PowerPoint, Word, Markdown hoặc MP3 nếu bạn yêu cầu.
**Why / Vì sao**: Google renders the file once so it looks the same on Mac, Windows, iPad and the browser / Google dựng file một lần nên hiển thị giống nhau trên Mac, Windows, iPad và trình duyệt. Files stay private in your Drive / File nằm riêng tư trong Drive của bạn.

---

## ⚠️ Limits / Giới hạn
- Scanned image-only PDFs not supported. / PDF scan (ảnh, không có chữ) không xử lý được.
- Video editing/generation out of scope. / Chỉnh sửa/tạo video ngoài phạm vi.
