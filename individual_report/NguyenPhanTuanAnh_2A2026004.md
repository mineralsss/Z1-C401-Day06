# Individual reflection — Nguyễn Phan Tuấn Anh (2A2026004)

## 1. Role
Conversational AI Engineer (Prompt Egnineering & LangGraph Workflow Designer)

## 2. Đóng góp cụ thể
- Thiết kế conversational flow 5 bước (chào hỏi -> hỏi và thu thập triệu chứng -> hỏi nhu cầu đặt lịch -> chọn bác sĩ và thông tin lịch -> xác nhận đặt lịch)
- Viết và định nghĩa các tool get_nearest_branch, get_suitable_availibility_doctor, get_today_date, get_all_specialties, calculate age
- Viết và định nghĩa toàn bộ các response format
- Viết toàn bộ rules
- Viết toàn bộ constraints
- Viết và định nghĩa các node, edges trong langgraph


## 3. SPEC mạnh/yếu
- Mạnh nhất: Nhận diện case "hiệu chứng chung chung" - Nhóm đã rất thực tế khi xác định AI không phải là bác sĩ và sẽ có lúc bế tắc trước các mô tả mơ hồ của người dùng.
- Yếu nhất: ROI — 3 kịch bản thiếu sự phân hóa về giả định vận hành. Phần ROI hiện tại đang bị đánh giá là "tuyến tính hóa" quá mức, chủ yếu thay đổi về con số tài chính mà chưa thay đổi về bản chất mô hình triển khai.

## 4. Đóng góp khác
- Raise ý kiến tạo tiền đề form chung khi chốt lịch đặt và làm cho nó có các trường giống như form của form đặt lịch hẹn trên web vinmec
- Đồng kiểm tra, thu gom, chỉnh sửa cùng Chí Bảo các file để tạo Spec-final

## 5. Điều học được
- Trước khi làm hackathon chỉ sử dụng langgraph nhưng ở mức độ không có fallback về một node phía trước khi một node fail, sau hackathon thu thập được kiến thức mới.

## 6. Nếu làm lại
Sẽ làm toàn bộ dự án sớm hơn, sẽ bắt đầu từ tối D5 vì kế hoạch ban đầu đề ra có nhiều chức năng, có frontend, backend có tích hợp OCR hỗ trợ trích xuất thông tin CCCD/BHYT, và hỗ trợ Android Auto / Apple Carplay cho đặt lịch chế độ rảnh tay qua Siri / Gemini

## 7. AI giúp gì / AI sai gì
- **Giúp:** dùng Gemini để phác thảo ý tưởng những tool cần viết, giúp phác thảo ROI, hỗ trợ format lại các ý tưởng và lời nói thô thành format báo cáo
- **Sai/mislead:** Gemini phác thảo những ý tưởng ROI nhưng khi bảo phác thảo cả phần tính toán thì những tính toán đó vô căn cứ, không có cơ sở -> Sửa lại và phải draft lại bản thảo 2 lần nữa
