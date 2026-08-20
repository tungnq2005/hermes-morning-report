# Kịch bản buổi bàn giao 30 phút / 30-Minute Handover Script

Mục tiêu (AC D3): sau buổi này, khách **tự thao tác được** các việc cơ bản.
Goal (D3 AC): after this session, the client can **operate the basics themselves**.

**Chuẩn bị trước / Prep beforehand**
- Gateway đang chạy trên VPS (`healthcheck_hermes.sh` → `ok:true`).
- Diễn tập luồng cài đặt đã pass: `python3 skills/guided-setup/scripts/selftest.py` (14/14). Chạy trước, đừng để khách là người phát hiện luồng gãy.
- Đã đăng nhập dashboard sẵn trên trình duyệt (khỏi dán token lúc demo).
- Mở sẵn Telegram với `@your_bot`.
- In/mở sẵn `chat-commands.md` cho khách.

---

## Phút 0–3 — Tổng quan / Overview
- Giải thích: trợ lý điều khiển 100% qua chat Telegram, không cần đụng server — **kể cả phần cài đặt và kết nối key**.
- Cho xem 2 khả năng: bản tin sáng + chuyển đổi tài liệu.

## Phút 3–8 — Cài đặt qua chat (để KHÁCH tự làm)
*Bỏ mục này nếu bạn đã nhập sẵn key ở bước 03/06 — nhưng vẫn cho khách xem câu lệnh để họ biết đường tự sửa sau này.*

1. Khách nhắn: *"Kiểm tra cài đặt giúp tôi"* → bot liệt kê cái gì đã kết nối, còn thiếu gì.
2. Nếu còn thiếu: khách nhắn *"Cài đặt giúp tôi"* và **tự làm theo** ngay tại buổi bàn giao — đây chính là bằng chứng "khách tự thao tác được".
3. Chỉ cho khách 2 điều dễ hiểu nhầm nhất:
   - key chỉ là một dòng chữ dài, copy đúng dòng đó là đủ;
   - sau khi bấm **Cho phép** ở Google, trang **báo lỗi không mở được là đúng** — copy nguyên đường link trên thanh địa chỉ dán vào chat.
4. Nhắc khách xoá tin nhắn có chứa client secret sau khi kết nối xong.

## Phút 8–14 — Morning Report (để KHÁCH tự bấm)
1. Khách nhắn: *"Chạy thử morning report ngay"* → chờ nhận bản tin text + audio MP3.
2. Trong lúc chờ, mở dashboard `http://127.0.0.1:18789/` cho xem cron job đang lên lịch (`Next run`).
3. Khách tự đổi chủ đề: *"Thêm chủ đề giá vàng"* → xác nhận.
4. Khách tự tạm dừng / bật lại: *"Tạm dừng morning report"* → bot xác nhận đã pause; rồi *"Bật lại morning report"* → bot xác nhận đã resume. Config giữ nguyên.
5. **Nối sang D2 — làm ngay trên bản tin vừa nhận**: khách nhắn *"Xuất bản tin sáng nay ra Google Docs"* → nhận link Google Docs + PDF, **không phải gửi lại file nào**. Nhắn lại lần nữa để cho khách thấy bot trả về đúng file cũ chứ không tạo bản trùng trong Drive. Nói thêm: muốn tự động thì *"Bản tin giá vàng thì lưu luôn vào Google Docs"* (mỗi ngày thêm 1 file trong Drive).

## Phút 14–22 — Document Conversion (để KHÁCH tự làm)
1. Khách kéo–thả 1 file Word vào chat + *"Chuyển thành PowerPoint"* → nhận **link Google Slides** kèm bản PDF. Mở link ngay trên máy khách (Mac/Windows đều được) để thấy layout giống hệt nhau.
2. Thử tiếp *"Xuất file này ra PDF"*, và *"Gửi mình cả file .pptx"* (file này export từ chính bản Google).
3. Thử *"Đọc tài liệu này thành audio"* → nhận MP3.
4. Nhắc giới hạn: file Google phải công khai (hoặc nằm trong tài khoản đã kết nối); PDF scan không được; deck > 10MB thì chỉ có link, không kèm PDF.

## Phút 22–26 — Vận hành & sự cố / Ops & troubleshooting
- Chỉ `chat-commands.md` (bảng lệnh 1 trang) — "cần gì cứ nhắn tự nhiên", có sẵn mục Cài đặt & chìa khoá.
- Nói rõ: hỏng key hay mất kết nối Google thì **tự sửa được trong chat** (*"Kiểm tra cài đặt giúp tôi"*), không cần gọi kỹ thuật.
- Với người quản trị: chỉ `operator-runbook` — restart gateway, xem log, đổi key, `healthcheck_hermes.sh`.
- Nói rõ known limitations (TTS keyless; client secret nằm trong lịch sử chat nếu kết nối Google qua chat).

## Phút 26–30 — Hỏi đáp & bàn giao tài liệu / Q&A & handoff
- Trao 4 tài liệu: `first-run-setup` (VI/EN), `user-guide` (VI/EN), `operator-runbook` (VI/EN), `chat-commands`.
- Xác nhận checklist nghiệm thu (bên dưới) đã đạt.
- Thống nhất mốc theo dõi ổn định 48h.

---

## Checklist nghiệm thu D3 / D3 acceptance checklist
- [ ] Gateway `active (running)`, tự lên sau reboot VPS (lingering=yes).
- [ ] Morning report gửi được text + audio 3–5 phút; cron đặt đúng giờ gửi đã cấu hình (theo timezone của khách).
- [ ] Doc-convert: docx↔pptx↔pdf + narrate chạy được qua chat; kết quả trả về link Google Slides/Docs mở đúng trên máy khách (kể cả macOS).
- [ ] Xuất bản tin sang Google Docs chạy được từ chat (*"Xuất bản tin sáng nay ra Google Docs"*), và lần hỏi thứ hai trả về đúng file cũ.
- [ ] `preflight.py --compact` → `google.authorized_token: true` (không có token thì kết quả bị render local, hiển thị lệch trên Mac).
- [ ] `secrets audit --check` → clean (plaintext=0).
- [ ] `healthcheck_hermes.sh` → `ok:true`.
- [ ] Ổn định ≥48h: ≥2 lần gửi sáng thành công, log không lỗi lặp.
- [ ] Khách tự thao tác được các việc cơ bản trong buổi này.
- [ ] Khách tự chạy được *"Kiểm tra cài đặt giúp tôi"* và hiểu phải làm gì khi bot báo thiếu key.
- [ ] `check_setup.py --verify` → không còn mục nào `invalid`; mọi key đang dùng đều được nhà cung cấp xác nhận.
- [ ] `selftest.py` → 14/14 PASS.
- [ ] Đã đi qua checklist 8b (Google thật) trong `google-oauth-setup.vi.md`, gồm cả 2 tình huống hỏng (dán chậm, dán nhầm).
- [ ] Đã bàn giao đủ tài liệu song ngữ.
