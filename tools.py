from __future__ import annotations

import json
import math
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func


ROOT_DIR = Path(__file__).resolve().parent
DB_CANDIDATES = [
    ROOT_DIR / "data" / "vinmec.sqlite",
    ROOT_DIR / "vinmec.sqlite3",
]


def _db_has_objects(path: Path, object_names: list[str]) -> bool:
    if not path.exists():
        return False
    try:
        with sqlite3.connect(path) as connection:
            cursor = connection.cursor()
            for name in object_names:
                found = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE (type='table' OR type='view') AND name = ?",
                    (name,),
                ).fetchone()
                if not found:
                    return False
            return True
    except sqlite3.Error:
        return False


def _resolve_db_path() -> Path:
    schedule_schema = ["doctors", "doctor_schedules", "doctor_schedule_slots", "vw_available_slots"]
    for candidate in DB_CANDIDATES:
        if _db_has_objects(candidate, schedule_schema):
            return candidate
    for candidate in DB_CANDIDATES:
        if candidate.exists():
            return candidate
    return DB_CANDIDATES[0]


DB_PATH = _resolve_db_path()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def get_user_location(location: str = "VinUni, Gia Lam, Ha Noi") -> str:
    """Geocode an input location and return "latitude,longitude"."""
    try:
        alias_map = {
            "vin uni": "VinUni, Gia Lam, Ha Noi",
            "vinuni": "VinUni, Gia Lam, Ha Noi",
            "vin university": "VinUni, Gia Lam, Ha Noi",
        }
        normalized = location.strip().lower()
        location = alias_map.get(normalized, location)

        query = urllib.parse.urlencode(
            {
                "q": location,
                "format": "jsonv2",
                "limit": 1,
            }
        )
        url = f"https://nominatim.openstreetmap.org/search?{query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "vinmec-assistant/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data:
            lat = data[0]["lat"]
            lon = data[0]["lon"]
            return f"{lat},{lon}"
        return ""
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError):
        return ""


def get_branch_coordinates() -> dict[str, tuple[float, float]]:
    """Read all facility/branch coordinates from current DB schema."""
    try:
        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.cursor()
            rows = []
            has_branches = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='branches'"
            ).fetchone()
            if has_branches:
                rows = cursor.execute(
                    "SELECT name, latitude, longitude FROM branches WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
                ).fetchall()

            if not rows:
                has_facilities = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='facilities'"
                ).fetchone()
                if has_facilities:
                    rows = cursor.execute(
                        "SELECT name, latitude, longitude FROM facilities WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
                    ).fetchall()
        return {name: (float(lat), float(lon)) for name, lat, lon in rows}
    except sqlite3.Error:
        return {}


def _normalize_day(day: str) -> str:
    text = (day or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


@tool
def get_nearest_branch(location: str = "VinUni, Gia Lam, Ha Noi", max_results: int = 3) -> str:
    """Return nearest branch names with distances from an input location."""
    try:
        if isinstance(location, dict):
            location = (
                location.get("location")
                or location.get("address")
                or location.get("query")
                or "VinUni, Gia Lam, Ha Noi"
            )
        elif location is None:
            location = "VinUni, Gia Lam, Ha Noi"
        else:
            location = str(location).strip() or "VinUni, Gia Lam, Ha Noi"

        # Accept either "lat,lon" or a free-text address/place name.
        try:
            user_lat, user_lon = map(float, location.split(","))
        except ValueError:
            user_location = get_user_location(location)
            if not user_location:
                return "Khong geocode duoc dia chi."
            user_lat, user_lon = map(float, user_location.split(","))

        branch_coords = get_branch_coordinates()
        if not branch_coords:
            return "Khong tim thay toa do chi nhanh trong database."

        ranked: list[tuple[str, float]] = []
        for branch_name, (branch_lat, branch_lon) in branch_coords.items():
            distance = _haversine_km(user_lat, user_lon, branch_lat, branch_lon)
            ranked.append((branch_name, distance))

        ranked.sort(key=lambda item: item[1])
        top = ranked[: max(1, int(max_results))]
        return "\n".join(f"{name}: {distance:.1f} km" for name, distance in top)
    except (ValueError, KeyError):
        return "Toa do dau vao khong hop le."

@tool
def get_suitable_availibility_doctor(day: str, shift: str, specialty: str = "", facility: str = "") -> str:
    """Return suitable available doctors for a given day, shift, and optional specialty/facility."""
    normalized_day = _normalize_day(day)
    specialty_filter = (specialty or "").strip().lower()
    facility_filter = (facility or "").strip().lower()
    query = """
    SELECT
    d.doctor_id,
    d.full_name AS doctor_name,
    f.facility_id,
    f.name AS facility_name,
    sch.shift,
    COUNT(v.slot_id) AS available_slot_count,
    MIN(v.start_at) AS first_available_time,
    MAX(v.end_at) AS last_available_time,
    GROUP_CONCAT(DISTINCT sp.name) AS specialties
    FROM vw_available_slots v
    JOIN doctors d
        ON d.doctor_id = v.doctor_id
    JOIN doctor_schedules sch
        ON sch.schedule_id = v.schedule_id
    JOIN facilities f
        ON f.facility_id = v.facility_id
    LEFT JOIN doctor_specialties ds
        ON ds.doctor_id = d.doctor_id
    LEFT JOIN specialties sp
        ON sp.specialty_id = ds.specialty_id
    WHERE v.slot_date = ?
    AND sch.shift = ?
    AND d.is_active = 1
    AND sch.status = 'active'
    AND (
        ? = ''
        OR LOWER(COALESCE(sp.name, '')) LIKE '%' || ? || '%'
        OR LOWER(COALESCE(sp.normalized_name, '')) LIKE '%' || ? || '%'
    )
    AND (
        ? = ''
        OR LOWER(f.name) LIKE '%' || ? || '%'
        OR LOWER(COALESCE(f.normalized_name, '')) LIKE '%' || ? || '%'
    )
    GROUP BY d.doctor_id, d.full_name, f.facility_id, f.name, sch.shift
    ORDER BY available_slot_count DESC, first_available_time ASC;
    """
    try:
        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.cursor()
            required_objects = [
                "vw_available_slots",
                "doctor_schedules",
                "doctor_specialties",
                "specialties",
                "facilities",
            ]
            missing = []
            for name in required_objects:
                found = cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE (type='table' OR type='view') AND name = ?",
                    (name,),
                ).fetchone()
                if not found:
                    missing.append(name)

            if missing:
                rows = cursor.execute(
                    "SELECT name, speciality FROM doctors ORDER BY name LIMIT 10"
                ).fetchall()
                if not rows:
                    return "Khong co du lieu bac si trong database hien tai."
                preview = "\n".join(
                    f"{name} | {speciality or 'N/A'}" for name, speciality in rows
                )
                return (
                    "Database hien tai chua co bang lich kham (doctor_schedules/slots), "
                    "nen chua loc duoc theo ngay/ca va chuyen khoa.\n"
                    "Danh sach bac si tham khao:\n"
                    f"{preview}"
                )

            cursor.execute(
                query,
                (
                    normalized_day,
                    shift,
                    specialty_filter,
                    specialty_filter,
                    specialty_filter,
                    facility_filter,
                    facility_filter,
                    facility_filter,
                ),
            )
            rows = cursor.fetchall()
        if not rows:
            extra_parts = []
            if specialty_filter:
                extra_parts.append(f"chuyen khoa '{specialty}'")
            if facility_filter:
                extra_parts.append(f"co so '{facility}'")
            extra = ", " + ", ".join(extra_parts) if extra_parts else ""
            return f"Khong tim thay bac si nao co lich trong ngay {normalized_day}, ca {shift}{extra}."
        return "\n".join(
            f"{row[1]} | {row[3]} | {row[4]} | slots: {row[5]} | {row[6]}-{row[7]} | {row[8] or 'N/A'}"
            for row in rows
        )
    except sqlite3.Error as exc:
        return f"Co loi xay ra khi truy van database: {exc}"

@tool
def get_today_date() -> str:
    """Return today's date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")
    
@tool
def calculate_age(birth_date: str) -> str:
    """Calculate age from birth date in YYYY-MM-DD format."""
    try:
        birth = datetime.strptime(birth_date, "%Y-%m-%d")
        today = datetime.now()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        return str(age)
    except ValueError:
        return "Birth date format should be YYYY-MM-DD."


@tool
def get_all_specialties(facility: str) -> str:
    """Return a list of all specialties in that facility."""
    try:
        with sqlite3.connect(DB_PATH) as connection:
            cursor = connection.cursor()
            query = """
            SELECT DISTINCT sp.name
            FROM specialties sp
            JOIN doctor_specialties ds ON ds.specialty_id = sp.specialty_id
            JOIN doctors d ON d.doctor_id = ds.doctor_id
            JOIN doctor_schedules sch ON sch.doctor_id = d.doctor_id
            JOIN facilities f ON f.facility_id = sch.facility_id
            WHERE f.name LIKE '%' || ? || '%'
            AND d.is_active = 1
            AND sch.status = 'active';
            """
            cursor.execute(query, (facility.strip().lower(),))
            rows = cursor.fetchall()
        if not rows:
            return f"Khong tim thay chuyen khoa nao trong co so '{facility}'."
        return "\n".join(row[0] for row in rows)
    except sqlite3.Error as exc:
        return f"Co loi xay ra khi truy van database: {exc}"


if __name__ == "__main__":
    day = "2026-04-09"
    shift = "morning"
    specialty = "tim mach"
    facility = "times city"
    print(get_all_specialties.invoke(facility))
DB_PATH = None
for path in DB_CANDIDATES:
    if path.exists():
        DB_PATH = path
        break

if DB_PATH is None:
    raise FileNotFoundError("Database file not found")


@tool
def get_doctor_schedule(doctor_name: str) -> str:
    """
    Trả về lịch làm việc của bác sĩ dựa trên tên.
    Input: tên bác sĩ (có thể nhập một phần tên, tiếng Việt)
    Output: danh sách ca làm việc với trạng thái còn chỗ hay hết chỗ
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT d.doctor_id, d.full_name
        FROM doctors d
        WHERE d.full_name LIKE ? OR d.normalized_name LIKE ?
    """, (f"%{doctor_name}%", f"%{doctor_name}%"))

    doctors = cursor.fetchall()

    if not doctors:
        conn.close()
        return f"Không tìm thấy bác sĩ nào có tên '{doctor_name}'."

    result = []

    for doc in doctors:
        doctor_id = doc["doctor_id"]
        full_name = doc["full_name"]
        result.append(f"📅 Lịch làm việc của bác sĩ {full_name}:\n")

        cursor.execute("""
            SELECT schedule_id, work_date, shift,
                   max_bookings, booked_count, status
            FROM doctor_schedules
            WHERE doctor_id = ?
            ORDER BY work_date
        """, (doctor_id,))

        schedules = cursor.fetchall()

        if not schedules:
            result.append("  Không có lịch làm việc.\n")
            continue

        for row in schedules:
            available = row["max_bookings"] - row["booked_count"]
            slot_status = "✅ Còn chỗ" if available > 0 else "❌ Hết chỗ"
            result.append(
                f"  - Ngày: {row['work_date']} | Ca: {row['shift']} "
                f"| Còn trống: {available}/{row['max_bookings']} "
                f"| {slot_status}"
            )
        result.append("")

    conn.close()
    return "\n".join(result)

from langchain_core.tools import tool

@tool
def confirm_appointment_summary(
    full_name: str,
    phone: str,
    specialty: str,
    facility: str,
    preferred_time: str,
    note: str = ""
) -> str:
    """
    Tóm tắt thông tin đặt lịch khám của bệnh nhân trước khi xác nhận.
    Dùng khi đã thu thập đủ thông tin từ người dùng để chốt lịch hẹn.

    Args:
        full_name: Họ tên đầy đủ của bệnh nhân
        phone: Số điện thoại liên hệ
        specialty: Chuyên khoa hoặc dịch vụ muốn khám
        facility: Cơ sở Vinmec mong muốn
        preferred_time: Thời gian mong muốn đặt lịch
        note: Ghi chú thêm (triệu chứng, yêu cầu đặc biệt,...)
    """
    missing = []
    if not full_name.strip():
        missing.append("Họ tên")
    if not phone.strip():
        missing.append("Số điện thoại")
    if not specialty.strip():
        missing.append("Chuyên khoa/dịch vụ")
    if not facility.strip():
        missing.append("Cơ sở Vinmec")
    if not preferred_time.strip():
        missing.append("Thời gian mong muốn")

    if missing:
        return (
            f"⚠️ Còn thiếu thông tin:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nVui lòng cung cấp thêm để tiếp tục."
        )

    return f"""
✅ Xác nhận thông tin đặt lịch khám tại Vinmec:

- Họ tên:               {full_name}
- Số điện thoại:        {phone}
- Chuyên khoa/dịch vụ: {specialty}
- Cơ sở Vinmec:        {facility}
- Thời gian mong muốn: {preferred_time}
- Ghi chú:             {note if note.strip() else "Không có"}

📌 Vui lòng xác nhận lại thông tin trên. Nếu chính xác, chúng tôi sẽ tiến hành đặt lịch cho bạn.
""".strip()


@tool
def book_appointment(
    full_name: str,
    phone: str,
    specialty: str,
    facility: str,
    preferred_date: str,
    shift: str,
    symptom_text: str = "",
    nationality_type: str = "local"
) -> str:
    """
    Đặt lịch khám và cập nhật database khi user xác nhận.
    Tìm schedule còn chỗ → tạo user nếu chưa có → tạo appointment → tăng booked_count.

    Args:
        full_name: Họ tên bệnh nhân
        phone: Số điện thoại
        specialty: Tên chuyên khoa
        facility: Tên cơ sở Vinmec
        preferred_date: Ngày muốn khám (YYYY-MM-DD)
        shift: Ca khám (morning/afternoon)
        symptom_text: Triệu chứng hoặc ghi chú
        nationality_type: 'local' hoặc 'foreign'
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # ── 1. Tìm facility ──────────────────────────────────────────
        cursor.execute("""
            SELECT facility_id, name FROM facilities
            WHERE name LIKE ? OR normalized_name LIKE ?
            LIMIT 1
        """, (f"%{facility}%", f"%{facility.lower()}%"))
        facility_row = cursor.fetchone()
        if not facility_row:
            return f"❌ Không tìm thấy cơ sở Vinmec: '{facility}'"
        facility_id = facility_row["facility_id"]
        facility_name = facility_row["name"]

        # ── 2. Tìm specialty ─────────────────────────────────────────
        cursor.execute("""
            SELECT specialty_id, name FROM specialties
            WHERE name LIKE ? OR normalized_name LIKE ?
            LIMIT 1
        """, (f"%{specialty}%", f"%{specialty.lower()}%"))
        specialty_row = cursor.fetchone()
        specialty_id = specialty_row["specialty_id"] if specialty_row else None

        # ── 3. Tìm schedule còn chỗ ──────────────────────────────────
        cursor.execute("""
            SELECT
                ds.schedule_id, ds.doctor_id,
                ds.work_date, ds.shift,
                ds.max_bookings, ds.booked_count,
                d.full_name as doctor_name,
                d.price_local, d.price_foreigner
            FROM doctor_schedules ds
            JOIN doctors d ON ds.doctor_id = d.doctor_id
            WHERE ds.work_date = ?
              AND ds.shift = ?
              AND ds.facility_id = ?
              AND ds.booked_count < ds.max_bookings
              AND ds.status = 'active'
            ORDER BY ds.schedule_id
            LIMIT 1
        """, (preferred_date, shift, facility_id))
        schedule = cursor.fetchone()

        if not schedule:
            return (
                f"❌ Không còn chỗ trống vào ngày {preferred_date} "
                f"ca {shift} tại {facility_name}.\n"
                f"Vui lòng chọn ngày hoặc ca khác."
            )

        schedule_id = schedule["schedule_id"]
        doctor_id   = schedule["doctor_id"]
        doctor_name = schedule["doctor_name"]
        fee = schedule["price_local"] if nationality_type == "local" else schedule["price_foreigner"]

        # ── 4. Tạo / lấy user ───────────────────────────────────────
        cursor.execute("SELECT user_id FROM users WHERE phone = ? LIMIT 1", (phone,))
        user_row = cursor.fetchone()

        if user_row:
            user_id = user_row["user_id"]
        else:
            cursor.execute("""
                INSERT INTO users (full_name, phone, nationality_type)
                VALUES (?, ?, ?)
            """, (full_name, phone, nationality_type))
            user_id = cursor.lastrowid

        # ── 5. Tạo appointment ───────────────────────────────────────
        cursor.execute("""
            INSERT INTO appointments (
                user_id, doctor_id, facility_id, specialty_id,
                schedule_id, symptom_text, nationality_type,
                consultation_fee, status, confirmed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', CURRENT_TIMESTAMP)
        """, (
            user_id, doctor_id, facility_id, specialty_id,
            schedule_id, symptom_text, nationality_type, fee
        ))
        appointment_id = cursor.lastrowid

        # ── 6. Tăng booked_count ─────────────────────────────────────
        cursor.execute("""
            UPDATE doctor_schedules
            SET booked_count = booked_count + 1
            WHERE schedule_id = ?
        """, (schedule_id,))

        conn.commit()

        return f"""
✅ Đặt lịch thành công! Mã lịch hẹn: #{appointment_id}

📋 Thông tin xác nhận:
- Họ tên:          {full_name}
- Số điện thoại:   {phone}
- Bác sĩ:          {doctor_name}
- Chuyên khoa:     {specialty}
- Cơ sở Vinmec:    {facility_name}
- Ngày khám:       {schedule['work_date']}
- Ca khám:         {schedule['shift']}
- Chi phí:         {fee:,} VNĐ
- Triệu chứng:     {symptom_text or 'Không có'}

📌 Vui lòng đến trước giờ hẹn 15 phút và mang theo CMND/CCCD.
""".strip()

    except Exception as e:
        conn.rollback()
        return f"❌ Lỗi khi đặt lịch: {str(e)}"

    finally:
        conn.close()


tools_list = [get_doctor_schedule, confirm_appointment_summary, book_appointment]
import sqlite3
from datetime import date
from pathlib import Path
from langchain_core.tools import tool

_DB_PATH = Path(__file__).resolve().parent / "data" / "vinmec.sqlite"
_TODAY = date.today().isoformat()  # "2026-04-09" — dạng TEXT khớp với DB


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@tool
def get_doctor_profile(doctor_name: str) -> dict:
    """
    Tìm và trả về thông tin của bác sĩ, bao gồm profile đầy đủ và lịch làm việc sắp tới.

    Args:
        doctor_name: Tên đầy đủ của bác sĩ (chính xác theo danh sách)

    Returns:
        Profile đầy đủ và lịch làm việc của bác sĩ.
    """
    with _get_connection() as conn:
        # --- Profile ---
        row = conn.execute(
            """
            SELECT d.doctor_id, d.full_name, d.degrees, d.description,
                   d.qualification, d.raw_speciality,
                   d.price_local, d.price_foreigner,
                   f.name AS facility_name
            FROM doctors d
            JOIN facilities f ON f.facility_id = d.facility_id
            WHERE d.full_name = ?
              AND d.profile_type = 'doctor'
            LIMIT 1
            """,
            (doctor_name,),
        ).fetchone()

        if row is None:
            return {"error": f"Không tìm thấy bác sĩ '{doctor_name}' trong hệ thống."}

        profile = {
            "name":            row["full_name"],
            "degrees":         row["degrees"] or "",
            "description":     row["description"] or "",
            "speciality":      row["raw_speciality"] or "",
            "qualification":   row["qualification"] or "",
            "vinmec_site":     row["facility_name"] or "",
            "price_local":     row["price_local"],
            "price_foreigner": row["price_foreigner"],
        }


    return {"profile": profile}
