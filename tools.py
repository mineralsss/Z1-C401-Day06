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

if __name__ == "__main__":
    day = "2026-04-09"
    shift = "morning"
    specialty = "tim mach"
    facility = "times city"
    if hasattr(get_suitable_availibility, "invoke"):
        print(
            get_suitable_availibility.invoke(
                {"day": day, "shift": shift, "specialty": specialty, "facility": facility}
            )
        )
    else:
        print(get_suitable_availibility(day, shift, specialty, facility))