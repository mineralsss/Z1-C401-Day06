# Báo cáo thiết kế SQLite — Agent đặt lịch khám

## Cách chạy

### 1. Tạo database

```bash
python scripts/create_db.py
```

Mặc định tạo DB tại `data/vinmec.sqlite`.

### 2. Import dữ liệu

```bash
python scripts/import_data.py
```

### Chạy lại từ đầu (reset DB)

Nếu schema thay đổi, cần xoá DB cũ trước rồi tạo lại:

```bash
# Linux / macOS
rm data/vinmec.sqlite
python scripts/create_db.py
python scripts/import_data.py
```

```powershell
# Windows (PowerShell)
Remove-Item data/vinmec.sqlite
python scripts/create_db.py
python scripts/import_data.py
```

> Lý do: `create_db.py` dùng `CREATE TABLE IF NOT EXISTS` nên không tự xoá schema cũ. Phải xoá file `.sqlite` thủ công khi có thay đổi cấu trúc bảng.

Các tham số:

| Tham số | Mặc định |
|---|---|
| `--db` | `data/vinmec.sqlite` |
| `--doctors` | `danh_sach_bac_si.csv` |
| `--facilities` | `danh_sach_co_so.csv` |
| `--specialties` | `chuyen_khoa.csv` |
| `--schedules` | `doctor_schedule.csv` |

### Kết quả import đã kiểm chứng

| Bảng | Số bản ghi |
|---|---|
| `facilities` | 11 |
| `specialties` | 73 |
| `doctors` | 524 |
| `doctor_specialties` | 447 |
| `doctor_schedules` | 4348 |
| `users` | 0 |
| `appointments` | 0 |

> `doctor_schedule.csv` có 4351 dòng, sau import còn 4348 do 3 dòng trùng unique key.

---

## Cấu trúc database

### `users`

Thông tin người dùng phục vụ đặt lịch.

| Cột | Ghi chú |
|---|---|
| `full_name`, `normalized_name` | Tên gốc và tên đã chuẩn hóa |
| `phone`, `email` | Có index |
| `date_of_birth`, `gender` | |
| `nationality_type` | `local` hoặc `foreigner` |
| `identity_no`, `address` | |

### `facilities`

Cơ sở khám chữa bệnh.

| Cột | Ghi chú |
|---|---|
| `name` | Tên gốc, unique |
| `normalized_name` | Tên đã chuẩn hóa, dùng để lookup |
| `address`, `province` | Province tách từ địa chỉ |
| `latitude`, `longitude` | Hiện để NULL, dự phòng tính khoảng cách |

### `specialties`

Danh mục chuyên khoa.

| Cột | Ghi chú |
|---|---|
| `source_specialty_id` | ID gốc từ `chuyen_khoa.csv` |
| `name`, `normalized_name` | |
| `is_master` | `1` = từ danh mục gốc, `0` = tạo thêm khi không map được |

### `doctors`

Hồ sơ bác sĩ.

| Cột | Ghi chú |
|---|---|
| `full_name`, `normalized_name` | |
| `degrees`, `description`, `qualification` | Thông tin hồ sơ |
| `raw_speciality` | Chuỗi chuyên khoa gốc từ CSV |
| `facility_id` | FK → `facilities` |
| `price_local`, `price_foreigner` | Giá khám theo loại bệnh nhân |
| `profile_type` | `doctor` / `service` / `unknown` |

Unique key: `(normalized_name, facility_id)`.

### `doctor_specialties`

Bảng nối `doctors` ↔ `specialties`.

### `doctor_schedules`

Mỗi dòng là một ca làm việc (sáng hoặc chiều) của bác sĩ trong một ngày.

| Cột | Ghi chú |
|---|---|
| `doctor_id`, `facility_id` | |
| `work_date` | Ngày làm việc |
| `shift` | `morning` / `afternoon` |
| `max_bookings` | Số chỗ tối đa, mặc định 50 |
| `booked_count` | Số người đã đặt, tăng/giảm theo appointment |
| `status` | `active` / `cancelled` — dùng để đánh dấu ca bị huỷ, không liên quan đến việc đầy chỗ |

Unique key: `(doctor_id, facility_id, work_date, shift)`.

Logic đặt lịch:
- Chỉ cho đặt khi `booked_count < max_bookings`
- Sau khi đặt thành công: `booked_count + 1`, nếu đầy thì `status = 'full'`
- Khi huỷ appointment: `booked_count - 1`, `status` về `active`

### `appointments`

Lịch hẹn đã đặt.

| Cột | Ghi chú |
|---|---|
| `user_id`, `doctor_id`, `facility_id`, `specialty_id` | |
| `schedule_id` | FK → `doctor_schedules` |
| `symptom_text`, `booking_note` | |
| `nationality_type` | Xác định giá khám |
| `consultation_fee` | Phí tại thời điểm đặt |
| `status` | `pending` / `confirmed` / `completed` / `cancelled` / `no_show` |

### View `vw_available_schedules`

Trả về các ca còn chỗ đặt (`status = 'active'` và `booked_count < max_bookings`), kèm số chỗ còn lại (`remaining_slots`). Dùng để agent tra cứu lịch trống khi người dùng muốn đặt khám.

### View `vw_appointment_detail`

Trả về toàn bộ thông tin chi tiết của một lịch hẹn: thông tin bệnh nhân, bác sĩ, cơ sở, chuyên khoa, ca làm việc, phí khám. Dùng để tra cứu lịch sử đặt khám hoặc hiển thị chi tiết cho người dùng.

---

## Chuẩn hóa dữ liệu

### Nguyên tắc chung

Dữ liệu gốc được giữ nguyên trong các cột `full_name`, `raw_speciality`, v.v. Cột `normalized_name` chỉ dùng cho lookup và dedup, không thay thế dữ liệu gốc.

### 1. Chuẩn hóa text (`normalize_text`)

Áp dụng cho tên bác sĩ, cơ sở, chuyên khoa trước khi lưu vào `normalized_name`:

1. Strip BOM (`\ufeff`), lowercase
2. Chuyển `đ/Đ` → `d/D` thủ công (trước bước NFKD để tránh mất ký tự)
3. `unicodedata.normalize("NFKD")` + bỏ combining characters → loại toàn bộ dấu
4. Xóa ký tự không phải `a-z0-9`, collapse whitespace

Ví dụ: `"Bệnh viện Đa khoa Quốc tế"` → `"benh vien da khoa quoc te"`

### 2. Matching cơ sở (`facility_lookup_key`)

Cùng một cơ sở có thể xuất hiện với nhiều cách viết khác nhau giữa các file CSV:

- Expand viết tắt: `dkqt` → `da khoa quoc te`
- Strip prefix chuẩn (ví dụ `benh vien da khoa quoc te vinmec `) để lấy phần định danh
- Nếu cơ sở chỉ xuất hiện trong file bác sĩ mà không có trong `danh_sach_co_so.csv`, script tự tạo bản ghi mới

### 3. Mapping chuyên khoa

Chuyên khoa trong CSV bác sĩ là free-text, không khớp exact với danh mục:

1. Normalize text
2. Tra bảng alias cứng (`SPECIALTY_ALIAS_TO_MASTER`, ~12 entry) để map về specialty master
3. Nếu không map được → tạo specialty mở rộng với `is_master=0` thay vì bỏ dữ liệu

Một số alias ví dụ:

| Giá trị trong CSV | Map về |
|---|---|
| `phu khoa`, `khoa san`, `san khoa` | `san phu khoa` |
| `tieu hoa`, `noi tieu hoa noi soi` | `noi tieu hoa` |
| `vaccine` | `tiem chung vac xin` |
| `ung buou xa tri` | `trung tam ung buou` |

### 4. Dedup bác sĩ trùng tên

`doctor_schedule.csv` chỉ có tên bác sĩ, không có `facility_id`. Khi một tên xuất hiện ở nhiều cơ sở, script chọn bản ghi có `completeness_score` cao nhất:

```
score = len(degrees) + len(speciality) + len(description) + len(qualification)
```

Có 4 trường hợp trùng tên đã được resolve theo rule này.

### 5. Logic đặt lịch theo ca

Mỗi ca (`doctor_schedules`) có `max_bookings = 50` chỗ. Khi đặt lịch:
1. Kiểm tra `booked_count < max_bookings`
2. Insert appointment → `UPDATE doctor_schedules SET booked_count = booked_count + 1`
3. Nếu `booked_count = max_bookings` → `status = 'full'`
4. Khi huỷ → `booked_count - 1`, `status = 'active'`
