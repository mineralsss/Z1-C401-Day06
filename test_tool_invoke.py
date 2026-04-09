from __future__ import annotations

from tools import book_appointment, get_doctor_schedule, confirm_appointment_summary

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

# ── Lấy dữ liệu thực từ DB ───────────────────────────────────────
def get_sample_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT s.slot_date, ds.shift, f.name as facility_name,
               sp.name as specialty_name, d.full_name as doctor_name
        FROM doctor_schedule_slots s
        JOIN doctor_schedules ds ON s.schedule_id = ds.schedule_id
        JOIN facilities f ON ds.facility_id = f.facility_id
        JOIN doctors d ON s.doctor_id = d.doctor_id
        LEFT JOIN doctor_specialties dsp ON d.doctor_id = dsp.doctor_id
        LEFT JOIN specialties sp ON dsp.specialty_id = sp.specialty_id
        WHERE s.status = 'available'
        LIMIT 1
    """)
    row = dict(c.fetchone())
    conn.close()
    return row

if __name__ == "__main__":
    sample = get_sample_data()
    print(f"📦 Sample data: {sample}\n")

    # ── TEST 1: get_doctor_schedule ───────────────────────────────
    print("=" * 60)
    print("TEST 1 - get_doctor_schedule.invoke()")
    result = get_doctor_schedule.invoke({
        "doctor_name": sample["doctor_name"].split()[-1]
    })
    print(result)

    # ── TEST 2: confirm_appointment_summary ───────────────────────
    print("\n" + "=" * 60)
    print("TEST 2 - confirm_appointment_summary.invoke()")
    result = confirm_appointment_summary.invoke({
        "full_name": "Nguyễn Văn Test",
        "phone": "0901111111",
        "specialty": sample["specialty_name"] or "Tim mạch",
        "facility": sample["facility_name"],
        "preferred_time": f"{sample['shift']} ngày {sample['slot_date']}",
        "note": "Đau đầu, mệt mỏi"
    })
    print(result)

    # ── TEST 3: book_appointment ──────────────────────────────────
    print("\n" + "=" * 60)
    print("TEST 3 - book_appointment.invoke()")
    result = book_appointment.invoke({
        "full_name": "Nguyễn Văn Test",
        "phone": "0901111111",
        "specialty": sample["specialty_name"] or "Tim mạch",
        "facility": sample["facility_name"],
        "preferred_date": sample["slot_date"],
        "shift": sample["shift"],
        "symptom_text": "Đau đầu, mệt mỏi",
        "nationality_type": "local"
    })
    print(result)

    # ── TEST 4: Facility không tồn tại ───────────────────────────
    print("\n" + "=" * 60)
    print("TEST 4 - book_appointment.invoke() - Facility sai")
    result = book_appointment.invoke({
        "full_name": "Trần Thị Test",
        "phone": "0902222222",
        "specialty": "Tim mạch",
        "facility": "Bệnh viện Đa khoa Quốc tế Vinmec Ocean Park 2",
        "preferred_date": sample["slot_date"],
        "shift": sample["shift"],
    })
    print(result)