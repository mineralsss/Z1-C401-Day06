# Individual reflection — Nguyễn Văn A (AI20K001)

## 1. Role
Tool builder. Phụ trách thiết kế và implement tool get_doctor_profile.
## 2. Đóng góp cụ thể
- Xây dựng tool get_doctor_profile (API + logic) để trả về thông tin bác sĩ (tên, degrees, qualification, speciality...)
- Thiết kế output JSON schema (profile) để LLM có thể parse và sử dụng trực tiếp
- Xử lý logic truy vấn database (JOIN giữa bảng doctors và facilities) và chuẩn hóa dữ liệu trả về (handle null field)

## 3. SPEC mạnh/yếu
- Mạnh nhất: Phần mapping dữ liệu từ database → JSON output rõ ràng, clean
→ các field được normalize (or "" nếu null) giúp tránh crash khi LLM parse
- Yếu nhất: SPEC thiếu phần xử lý fuzzy search / input linh hoạt
→ hiện tại query dùng WHERE full_name = ? nên chỉ match chính xác
→ nếu user nhập sai tên hoặc thiếu dấu → tool fail ngay

## 4. Đóng góp khác
- Debug lỗi kết nối database và path (_DB_PATH) trong môi trường local
- Test nhiều input khác nhau để kiểm tra behavior khi có/không có dữ liệu
- Hỗ trợ team xử lý lỗi khi tool trả về { "error": ... } nhưng LLM chưa handle đúng

## 5. Điều học được
Trước hackathon nghĩ tool chỉ cần trả đúng data là đủ.
Sau khi làm mới hiểu: với AI system, format và consistency của output quan trọng hơn cả — chỉ cần lệch schema một chút là LLM có thể dùng sai hoặc không dùng được tool.

## 6. Nếu làm lại
- Sẽ implement fuzzy search (LIKE / full-text search) thay vì exact match để tăng UX
- Thêm phần trả về nhiều kết quả hơn (top-k doctors) thay vì chỉ LIMIT 1
- Chuẩn hóa error response (ví dụ: thêm error code thay vì chỉ string) để LLM xử lý tốt hơn

## 7. AI giúp gì / AI sai gì
- **Giúp:** Generate nhanh query SQL và boilerplate code cho tool
    Gợi ý cách dùng sqlite3.Row để access dữ liệu dạng dict
    Hỗ trợ debug lỗi syntax và structure của code mà nhóm không nghĩ ra. Dùng Gemini để test prompt nhanh qua AI Studio.

- **Sai/mislead:** Gợi ý query quá “lý tưởng” (assume dữ liệu luôn clean và     match chính xác)
    Không nhấn mạnh vấn đề UX như fuzzy search hoặc multiple results
    Đề xuất return data nhưng không nghĩ đến cách LLM sẽ consume (schema design chưa tối ưu)
