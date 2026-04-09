# Individual reflection — Nguyễn Phan Tuấn Anh (2A2026004)

## 1. Role
Prompt Engineer, 

## 2. Đóng góp cụ thể
- Thiết kế conversational flow 5 bước (chào hỏi -> hỏi và thu thập triệu chứng -> hỏi nhu cầu đặt lịch -> chọn bác sĩ và thông tin lịch -> xác nhận đặt lịch)
- Viết và định nghĩa các tool get_nearest_branch, get_suitable_availibility_doctor, get_today_date, get_all_specialties, calculate age
- Viết và định nghĩa toàn bộ các response format
- Viết toàn bộ rules
- Viết toàn bộ constraints
- Viết và định nghĩa các node, edges trong langgraph


## 3. SPEC mạnh/yếu
- Mạnh nhất: failure modes — nhóm nghĩ ra được case "triệu chứng chung chung"
  mà AI gợi ý quá rộng, và có mitigation cụ thể (hỏi thêm câu follow-up)
- Yếu nhất: ROI — 3 kịch bản thực ra chỉ khác số user, assumption gần giống nhau.
  Nên tách assumption rõ hơn (VD: conservative = chỉ dùng ở 1 chi nhánh,
  optimistic = rollout toàn hệ thống)

## 4. Đóng góp khác
- Test prompt với 10 triệu chứng khác nhau, ghi log kết quả vào prompt-tests.md
- Giúp Châu debug eval metrics — ban đầu chỉ có "accuracy" chung,
  sau tách ra precision cho từng khoa

## 5. Điều học được
Trước hackathon nghĩ precision và recall chỉ là metric kỹ thuật.
Sau khi thiết kế AI triage mới hiểu: chọn recall cao hơn cho khoa cấp cứu
(bỏ sót nguy hiểm hơn false alarm) nhưng precision cao hơn cho khoa chuyên sâu
(gợi ý sai gây lãng phí thời gian bệnh nhân). Metric là product decision,
không chỉ engineering decision.

## 6. Nếu làm lại
Sẽ test prompt sớm hơn — ngày đầu chỉ viết SPEC, đến trưa D6 mới bắt đầu test prompt.
Nếu test sớm từ tối D5 thì có thể iterate thêm 2-3 vòng, prompt sẽ tốt hơn nhiều.

## 7. AI giúp gì / AI sai gì
- **Giúp:** dùng Claude để brainstorm failure modes — nó gợi ý được "drug interaction"
  mà nhóm không nghĩ ra. Dùng Gemini để test prompt nhanh qua AI Studio.
- **Sai/mislead:** Claude gợi ý thêm feature "đặt lịch khám" vào chatbot —
  nghe hay nhưng scope quá lớn cho hackathon. Suýt bị scope creep nếu không dừng lại.
  Bài học: AI brainstorm tốt nhưng không biết giới hạn scope.