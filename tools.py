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
    Input: tên bác sĩ (nhập đúng và đủ tên bác sĩ, tiếng Việt)
    Output: danh sách ca làm việc với trạng thái slot còn trống hay đã đặt
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Tìm bác sĩ khớp tên (không phân biệt hoa thường)
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

    for doctor_id, full_name in doctors:
        result.append(f"📅 Lịch làm việc của bác sĩ {full_name}:\n")

        cursor.execute("""
            SELECT ds.work_date, ds.shift, ds.start_at, ds.end_at, ds.status,
                   COUNT(s.slot_id) as total_slots,
                   SUM(CASE WHEN s.status = 'available' THEN 1 ELSE 0 END) as available_slots
            FROM doctor_schedules ds
            LEFT JOIN doctor_schedule_slots s ON s.schedule_id = ds.schedule_id
            WHERE ds.doctor_id = ?
            GROUP BY ds.schedule_id
            ORDER BY ds.work_date, ds.start_at
        """, (doctor_id,))

        schedules = cursor.fetchall()

        if not schedules:
            result.append("  Không có lịch làm việc.\n")
            continue

        for row in schedules:
            work_date, shift, start_at, end_at, status, total, available = row
            available = available or 0
            booked = total - available
            slot_status = "✅ Còn chỗ" if available > 0 else "❌ Hết chỗ"
            result.append(
                f"  - Ngày: {work_date} | Ca: {shift} "
                f"| Giờ: {start_at} - {end_at} "
                f"| Còn trống: {available}/{total} (Đã đặt: {booked}) "
                f"| {slot_status}"
            )

        result.append("")

    conn.close()
    return "\n".join(result)
tools_list = [get_doctor_schedule]


if __name__ == "__main__":
    # Lấy 1 tên bác sĩ thực từ DB để test
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT full_name FROM doctors LIMIT 3")
    sample_doctors = [row[0] for row in c.fetchall()]
    conn.close()

    print("=" * 60)
    print("🔍 Test với tên bác sĩ thực từ DB:")
    print(f"  Sample names: {sample_doctors}\n")

    # Test 1: Tên đầy đủ
    name = sample_doctors[0].split()[-1]  # Lấy họ/tên cuối
    print(f"TEST 1 - Tìm theo '{name}':")
    print(get_doctor_schedule.invoke({"doctor_name": name}))

    # Test 2: Không tìm thấy
    print("=" * 60)
    print("TEST 2 - Tên không tồn tại:")
    print(get_doctor_schedule.invoke({"doctor_name": "Nguyễn Văn Không Tồn Tại"}))

    # Test 3: Tên một phần
    print("=" * 60)
    partial = sample_doctors[1].split()[1] if len(sample_doctors) > 1 else "An"
    print(f"TEST 3 - Tìm theo tên một phần '{partial}':")
    print(get_doctor_schedule.invoke({"doctor_name": partial}))