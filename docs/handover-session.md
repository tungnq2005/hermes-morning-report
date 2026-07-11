# Kịch bản buổi bàn giao 30 phút / 30-Minute Handover Script

Mục tiêu (AC D3): sau buổi này, khách **tự thao tác được** các việc cơ bản.
Goal (D3 AC): after this session, the client can **operate the basics themselves**.

**Chuẩn bị trước / Prep beforehand**
- Gateway đang chạy trên VPS (`healthcheck.sh` → `ok:true`).
- Đã đăng nhập dashboard sẵn trên trình duyệt (khỏi dán token lúc demo).
- Mở sẵn Telegram với `@your_bot`.
- In/mở sẵn `chat-commands.md` cho khách.

---

## Phút 0–3 — Tổng quan / Overview
- Giải thích: trợ lý điều khiển 100% qua chat Telegram, không cần đụng server.
- Cho xem 2 khả năng: bản tin sáng + chuyển đổi tài liệu.

## Phút 3–10 — Morning Report (để KHÁCH tự bấm)
1. Khách nhắn: *"Chạy thử morning report ngay"* → chờ nhận bản tin text + audio MP3.
2. Trong lúc chờ, mở dashboard `http://127.0.0.1:18789/` cho xem cron job đang lên lịch (`Next run`).
3. Khách tự đổi chủ đề: *"Thêm chủ đề giá vàng"* → xác nhận.
4. Khách tự tạm dừng / bật lại: *"Tạm dừng morning report"* → bot xác nhận đã pause; rồi *"Bật lại morning report"* → bot xác nhận đã resume. Config giữ nguyên.

## Phút 10–20 — Document Conversion (để KHÁCH tự làm)
1. Khách kéo–thả 1 file Word vào chat + *"Chuyển thành PowerPoint"* → nhận .pptx.
2. Thử tiếp *"Xuất file này ra PDF"*.
3. Thử *"Đọc tài liệu này thành audio"* → nhận MP3.
4. Nhắc giới hạn: file Google phải công khai; PDF scan không được.

## Phút 20–25 — Vận hành & sự cố / Ops & troubleshooting
- Chỉ `chat-commands.md` (bảng lệnh 1 trang) — "cần gì cứ nhắn tự nhiên".
- Với người quản trị: chỉ `operator-runbook` — restart gateway, xem log, đổi key, `healthcheck.sh`.
- Nói rõ known limitations (TTS keyless, Google riêng tư chưa có).

## Phút 25–30 — Hỏi đáp & bàn giao tài liệu / Q&A & handoff
- Trao 3 tài liệu: `user-guide` (VI/EN), `operator-runbook` (VI/EN), `chat-commands`.
- Xác nhận checklist nghiệm thu (bên dưới) đã đạt.
- Thống nhất mốc theo dõi ổn định 48h.

---

## Checklist nghiệm thu D3 / D3 acceptance checklist
- [ ] Gateway `active (running)`, tự lên sau reboot VPS (lingering=yes).
- [ ] Morning report gửi được text + audio 3–5 phút; cron đặt đúng giờ gửi đã cấu hình (theo timezone của khách).
- [ ] Doc-convert: docx↔pptx↔pdf + narrate chạy được qua chat.
- [ ] `secrets audit --check` → clean (plaintext=0).
- [ ] `healthcheck.sh` → `ok:true`.
- [ ] Ổn định ≥48h: ≥2 lần gửi sáng thành công, log không lỗi lặp.
- [ ] Khách tự thao tác được các việc cơ bản trong buổi này.
- [ ] Đã bàn giao đủ tài liệu song ngữ.
