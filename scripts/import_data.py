from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "vinmec.sqlite"
DEFAULT_DOCTORS_CSV = ROOT_DIR / "data_csv" / "danh_sach_bac_si.csv"
DEFAULT_FACILITIES_CSV = ROOT_DIR / "data_csv" / "danh_sach_co_so.csv"
DEFAULT_SPECIALTIES_CSV = ROOT_DIR / "data_csv" / "chuyen_khoa.csv"
DEFAULT_SCHEDULES_CSV = ROOT_DIR / "data_csv" / "doctor_schedule.csv"

FACILITY_PREFIXES = (
    "benh vien da khoa quoc te vinmec ",
    "benh vien da khoa vinmec ",
    "benh vien dkqt vinmec ",
    "phong kham da khoa quoc te vinmec ",
    "phong kham dkqt vinmec ",
)

FACILITY_COORDINATES_BY_KEY = {
    "times city": (20.9938194, 105.8671963),
    "smart city": (21.0079133, 105.7471695),
    "central park": (10.7940524, 106.7203681),
    "ha long": (20.9520499, 107.0719397),
    "hai phong": (20.8232825, 106.6879856),
    "nha trang": (12.2126502, 109.2107161),
    "phu quoc": (10.3366819, 103.8566615),
    "da nang": (16.0387756, 108.2112996),
    "can tho": (10.0260810, 105.7699584),
    "ocean park 2": (20.9396981, 105.9899806),
    "grand park": (20.9907222, 105.9560000),
}

SPECIALTY_ALIAS_TO_MASTER = {
    "gay me": "gay me dieu tri dau",
    "di ung mien dich lam sang": "hen di ung mien dich",
    "mien dich di ung": "hen di ung mien dich",
    "kham suc khoe tong quat": "kham suc khoe tong quat nguoi lon",
    "khoa phu": "san phu khoa",
    "phu khoa": "san phu khoa",
    "khoa san": "san phu khoa",
    "san khoa": "san phu khoa",
    "khoa vu": "trung tam benh ly vu",
    "ung buou xa tri": "trung tam ung buou",
    "vaccine": "tiem chung vac xin",
    "noi tieu hoa noi soi": "noi tieu hoa",
    "tieu hoa": "noi tieu hoa",
}


@dataclass
class ImportSummary:
    facilities_created: int = 0
    facilities_updated: int = 0
    specialties_created: int = 0
    specialties_updated: int = 0
    specialties_extended: int = 0
    doctors_created: int = 0
    doctors_updated: int = 0
    doctor_specialties_linked: int = 0
    schedules_created: int = 0
    schedules_updated: int = 0
    slots_created: int = 0
    slots_skipped: int = 0
    ambiguous_schedule_names: int = 0
    schedule_rows_skipped: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import normalized CSV data into SQLite.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the SQLite database file.")
    parser.add_argument("--doctors", type=Path, default=DEFAULT_DOCTORS_CSV, help="Path to the doctor CSV.")
    parser.add_argument("--facilities", type=Path, default=DEFAULT_FACILITIES_CSV, help="Path to the facility CSV.")
    parser.add_argument("--specialties", type=Path, default=DEFAULT_SPECIALTIES_CSV, help="Path to the specialty CSV.")
    parser.add_argument("--schedules", type=Path, default=DEFAULT_SCHEDULES_CSV, help="Path to the doctor schedule CSV.")
    parser.add_argument("--slot-minutes", type=int, default=30, help="Minutes per generated appointment slot.")
    parser.add_argument(
        "--google-api-key",
        type=str,
        default=os.getenv("GOOGLE_API_KEY", ""),
        help="Google Geocoding API key used by geocoder.google (or set GOOGLE_API_KEY env var).",
    )
    return parser.parse_args()


def normalize_text(value: str | None) -> str:
    text = (value or "").replace("\ufeff", "").strip().lower()
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    text = value.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def clean_nullable_text(value: str | None) -> str | None:
    text = clean_text(value)
    return text or None


def clean_name(value: str | None) -> str:
    return clean_text(value)


def parse_int(value: str | None) -> int:
    text = re.sub(r"[^\d]", "", value or "")
    return int(text) if text else 0


def facility_lookup_key(name: str) -> str:
    normalized = normalize_text(name)
    normalized = normalized.replace(" dkqt ", " da khoa quoc te ")
    for prefix in FACILITY_PREFIXES:
        if normalized.startswith(prefix):
            return normalized[len(prefix) :].strip()
    return normalized


def extract_province(address: str | None) -> str | None:
    if not address:
        return None
    parts = [part.strip() for part in clean_text(address).split(",") if part.strip()]
    for part in reversed(parts):
        normalized = normalize_text(part)
        if normalized == "viet nam":
            continue
        return part
    return None


def geocode_google_facility(
    facility_name: str,
    address: str | None,
    api_key: str,
) -> tuple[float | None, float | None]:
    """Resolve latitude/longitude for a facility with provider fallback."""

    # Use known facility coordinates first for stable/no-network imports.
    key = facility_lookup_key(facility_name)
    known = FACILITY_COORDINATES_BY_KEY.get(key)
    if known is not None:
        return known

    try:
        import geocoder
    except ImportError:
        geocoder = None

    query_candidates = [candidate for candidate in (address, facility_name) if candidate]

    # Prefer Google when a key is available.
    if api_key and geocoder is not None:
        for query in query_candidates:
            full_query = f"{query}, Viet Nam"
            try:
                result = geocoder.google(full_query, key=api_key)
            except Exception:
                continue
            if result and result.ok and result.latlng:
                lat, lng = result.latlng
                try:
                    return (float(lat), float(lng))
                except (TypeError, ValueError):
                    continue

    # No-key fallback via Open-Meteo geocoding API.
    for query in query_candidates:
        request_query = urllib.parse.urlencode(
            {
                "name": f"{query}, Viet Nam",
                "count": 1,
                "language": "en",
                "format": "json",
            }
        )
        url = f"https://geocoding-api.open-meteo.com/v1/search?{request_query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "vinmec-importer/1.0",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            continue

        results = payload.get("results") or []
        if not results:
            continue
        first = results[0]
        lat = first.get("latitude")
        lng = first.get("longitude")
        try:
            return (float(lat), float(lng))
        except (TypeError, ValueError):
                continue

    return (None, None)


def split_specialties(value: str | None) -> list[str]:
    text = clean_text(value)
    if not text:
        return []

    tokens: list[str] = []
    buffer: list[str] = []
    depth = 0

    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1

        if char == "," and depth == 0:
            token = "".join(buffer).strip()
            if token:
                tokens.append(token)
            buffer = []
            continue

        buffer.append(char)

    token = "".join(buffer).strip()
    if token:
        tokens.append(token)
    return tokens


def classify_profile_type(row: dict[str, str]) -> str:
    name_key = normalize_text(row.get("name"))
    has_profile_content = any(
        clean_text(row.get(field))
        for field in ("degrees", "description", "qualification", "speciality")
    )

    if not has_profile_content:
        return "unknown"

    service_keywords = ("health check", "service line", "kham suc khoe")
    if any(keyword in name_key for keyword in service_keywords):
        return "service"

    return "doctor"


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def configure_connection(connection: sqlite3.Connection, db_path: Path) -> None:
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = MEMORY;")
        connection.execute("PRAGMA synchronous = OFF;")
    except sqlite3.OperationalError:
        journal_path = db_path.with_name(f"{db_path.name}-journal")
        if journal_path.exists():
            journal_path.unlink()
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = MEMORY;")
            connection.execute("PRAGMA synchronous = OFF;")
            return
        raise


def ensure_database_ready(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found. Run create_db.py first: {db_path}")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    configure_connection(connection, db_path)
    return connection


def upsert_facility(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    *,
    name: str,
    address: str | None,
    province: str | None,
    latitude: float | None,
    longitude: float | None,
) -> int:
    normalized_name = normalize_text(name)
    existing = connection.execute(
        "SELECT facility_id FROM facilities WHERE normalized_name = ?",
        (normalized_name,),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO facilities (name, normalized_name, address, province, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, normalized_name, address, province, latitude, longitude),
        )
        summary.facilities_created += 1
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE facilities
        SET name = ?,
            address = COALESCE(?, address),
            province = COALESCE(?, province),
            latitude = COALESCE(?, latitude),
            longitude = COALESCE(?, longitude)
        WHERE facility_id = ?
        """,
        (name, address, province, latitude, longitude, existing["facility_id"]),
    )
    summary.facilities_updated += 1
    return int(existing["facility_id"])


def get_or_create_facility(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    facility_key_to_id: dict[str, int],
    site_name: str,
    google_api_key: str,
) -> int:
    key = facility_lookup_key(site_name)
    facility_id = facility_key_to_id.get(key)
    if facility_id is not None:
        return facility_id

    latitude, longitude = geocode_google_facility(site_name, None, google_api_key)
    facility_id = upsert_facility(
        connection,
        summary,
        name=site_name,
        address=None,
        province=None,
        latitude=latitude,
        longitude=longitude,
    )
    facility_key_to_id[key] = facility_id
    return facility_id


def upsert_specialty(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    *,
    name: str,
    source_specialty_id: int | None,
    is_master: int,
) -> int:
    normalized_name = normalize_text(name)
    existing = connection.execute(
        "SELECT specialty_id FROM specialties WHERE normalized_name = ?",
        (normalized_name,),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO specialties (source_specialty_id, name, normalized_name, is_master)
            VALUES (?, ?, ?, ?)
            """,
            (source_specialty_id, name, normalized_name, is_master),
        )
        if is_master:
            summary.specialties_created += 1
        else:
            summary.specialties_extended += 1
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE specialties
        SET name = ?,
            source_specialty_id = COALESCE(source_specialty_id, ?),
            is_master = CASE WHEN ? = 1 THEN 1 ELSE is_master END
        WHERE specialty_id = ?
        """,
        (name, source_specialty_id, is_master, existing["specialty_id"]),
    )
    if is_master:
        summary.specialties_updated += 1
    return int(existing["specialty_id"])


def load_specialty_lookup(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute("SELECT specialty_id, normalized_name FROM specialties").fetchall()
    return {row["normalized_name"]: int(row["specialty_id"]) for row in rows}


def resolve_specialty_id(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    specialty_lookup: dict[str, int],
    specialty_name: str,
) -> int:
    normalized_name = normalize_text(specialty_name)
    normalized_name = SPECIALTY_ALIAS_TO_MASTER.get(normalized_name, normalized_name)

    specialty_id = specialty_lookup.get(normalized_name)
    if specialty_id is not None:
        return specialty_id

    specialty_id = upsert_specialty(
        connection,
        summary,
        name=specialty_name,
        source_specialty_id=None,
        is_master=0,
    )
    specialty_lookup[normalize_text(specialty_name)] = specialty_id
    specialty_lookup[normalized_name] = specialty_id
    return specialty_id


def doctor_completeness_score(row: dict[str, str]) -> tuple[int, int]:
    score = sum(len(clean_text(row.get(field))) for field in ("degrees", "speciality", "description", "qualification"))
    facility_weight = len(clean_text(row.get("vinmec_site")))
    return (score, facility_weight)


def upsert_doctor(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    *,
    full_name: str,
    degrees: str | None,
    description: str | None,
    qualification: str | None,
    raw_speciality: str | None,
    facility_id: int,
    price_local: int,
    price_foreigner: int,
    profile_type: str,
) -> int:
    normalized_name = normalize_text(full_name)
    existing = connection.execute(
        """
        SELECT doctor_id
        FROM doctors
        WHERE normalized_name = ? AND facility_id = ?
        """,
        (normalized_name, facility_id),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO doctors (
                full_name,
                normalized_name,
                degrees,
                description,
                qualification,
                raw_speciality,
                facility_id,
                price_local,
                price_foreigner,
                profile_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                full_name,
                normalized_name,
                degrees,
                description,
                qualification,
                raw_speciality,
                facility_id,
                price_local,
                price_foreigner,
                profile_type,
            ),
        )
        summary.doctors_created += 1
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE doctors
        SET full_name = ?,
            degrees = ?,
            description = ?,
            qualification = ?,
            raw_speciality = ?,
            price_local = ?,
            price_foreigner = ?,
            profile_type = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE doctor_id = ?
        """,
        (
            full_name,
            degrees,
            description,
            qualification,
            raw_speciality,
            price_local,
            price_foreigner,
            profile_type,
            existing["doctor_id"],
        ),
    )
    summary.doctors_updated += 1
    return int(existing["doctor_id"])


def upsert_schedule(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    *,
    doctor_id: int,
    facility_id: int,
    work_date: str,
    shift: str,
    start_at: str,
    end_at: str,
) -> int:
    existing = connection.execute(
        """
        SELECT schedule_id
        FROM doctor_schedules
        WHERE doctor_id = ? AND work_date = ? AND shift = ? AND start_at = ? AND end_at = ?
        """,
        (doctor_id, work_date, shift, start_at, end_at),
    ).fetchone()

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO doctor_schedules (
                doctor_id, facility_id, work_date, shift, start_at, end_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doctor_id, facility_id, work_date, shift, start_at, end_at),
        )
        summary.schedules_created += 1
        return int(cursor.lastrowid)

    connection.execute(
        """
        UPDATE doctor_schedules
        SET facility_id = ?,
            status = 'active'
        WHERE schedule_id = ?
        """,
        (facility_id, existing["schedule_id"]),
    )
    summary.schedules_updated += 1
    return int(existing["schedule_id"])


def ensure_slots(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    *,
    schedule_id: int,
    doctor_id: int,
    work_date: str,
    start_at: str,
    end_at: str,
    slot_minutes: int,
) -> None:
    start_dt = datetime.fromisoformat(start_at)
    end_dt = datetime.fromisoformat(end_at)
    current = start_dt

    while current < end_dt:
        next_dt = current + timedelta(minutes=slot_minutes)
        if next_dt > end_dt:
            break

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO doctor_schedule_slots (
                schedule_id, doctor_id, slot_date, start_at, end_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                schedule_id,
                doctor_id,
                work_date,
                current.isoformat(sep=" "),
                next_dt.isoformat(sep=" "),
            ),
        )
        if cursor.rowcount == 1:
            summary.slots_created += 1
        else:
            summary.slots_skipped += 1
        current = next_dt


def import_facilities(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    facilities_csv: Path,
    google_api_key: str,
) -> dict[str, int]:
    facility_key_to_id: dict[str, int] = {}

    for row in load_csv_rows(facilities_csv):
        name = clean_name(row.get("name"))
        address = clean_nullable_text(row.get("address"))
        province = extract_province(address)
        latitude, longitude = geocode_google_facility(name, address, google_api_key)
        facility_id = upsert_facility(
            connection,
            summary,
            name=name,
            address=address,
            province=province,
            latitude=latitude,
            longitude=longitude,
        )
        facility_key_to_id[facility_lookup_key(name)] = facility_id

    return facility_key_to_id


def import_specialties(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    specialties_csv: Path,
) -> dict[str, int]:
    for row in load_csv_rows(specialties_csv):
        specialty_name = clean_name(row.get("name"))
        source_specialty_id = int(row["id"])
        upsert_specialty(
            connection,
            summary,
            name=specialty_name,
            source_specialty_id=source_specialty_id,
            is_master=1,
        )

    return load_specialty_lookup(connection)


def import_doctors(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    doctors_csv: Path,
    facility_key_to_id: dict[str, int],
    specialty_lookup: dict[str, int],
    google_api_key: str,
) -> dict[str, list[dict[str, int | tuple[int, int]]]]:
    doctor_name_candidates: dict[str, list[dict[str, int | tuple[int, int]]]] = defaultdict(list)

    for row in load_csv_rows(doctors_csv):
        full_name = clean_name(row.get("name"))
        facility_id = get_or_create_facility(
            connection,
            summary,
            facility_key_to_id,
            clean_name(row.get("vinmec_site")),
            google_api_key,
        )

        doctor_id = upsert_doctor(
            connection,
            summary,
            full_name=full_name,
            degrees=clean_nullable_text(row.get("degrees")),
            description=clean_nullable_text(row.get("description")),
            qualification=clean_nullable_text(row.get("qualification")),
            raw_speciality=clean_nullable_text(row.get("speciality")),
            facility_id=facility_id,
            price_local=parse_int(row.get("price_local")),
            price_foreigner=parse_int(row.get("price_foreigner")),
            profile_type=classify_profile_type(row),
        )

        for specialty_name in split_specialties(row.get("speciality")):
            specialty_id = resolve_specialty_id(connection, summary, specialty_lookup, specialty_name)
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO doctor_specialties (doctor_id, specialty_id)
                VALUES (?, ?)
                """,
                (doctor_id, specialty_id),
            )
            if cursor.rowcount == 1:
                summary.doctor_specialties_linked += 1

        doctor_name_candidates[normalize_text(full_name)].append(
            {
                "doctor_id": doctor_id,
                "facility_id": facility_id,
                "score": doctor_completeness_score(row),
            }
        )

    return doctor_name_candidates


def import_schedules(
    connection: sqlite3.Connection,
    summary: ImportSummary,
    schedules_csv: Path,
    doctor_name_candidates: dict[str, list[dict[str, int | tuple[int, int]]]],
    slot_minutes: int,
) -> None:
    schedule_rows = load_csv_rows(schedules_csv)
    schedule_name_keys = {normalize_text(row.get("name")) for row in schedule_rows}

    ambiguous_name_keys = 0
    for doctor_key, candidates in doctor_name_candidates.items():
        if len(candidates) > 1 and doctor_key in schedule_name_keys:
            ambiguous_name_keys += 1
            candidates.sort(
                key=lambda item: (
                    item["score"][0],  # type: ignore[index]
                    item["score"][1],  # type: ignore[index]
                    -int(item["doctor_id"]),
                ),
                reverse=True,
            )
    summary.ambiguous_schedule_names = ambiguous_name_keys

    for row in schedule_rows:
        doctor_key = normalize_text(row.get("name"))
        candidates = doctor_name_candidates.get(doctor_key)
        if not candidates:
            summary.schedule_rows_skipped += 1
            continue

        chosen = candidates[0]
        doctor_id = int(chosen["doctor_id"])
        facility_id = int(chosen["facility_id"])
        work_date = clean_name(row.get("working_day"))
        shift = clean_name(row.get("shift")) or "custom"
        start_at = clean_name(row.get("start_time"))
        end_at = clean_name(row.get("end_time"))

        schedule_id = upsert_schedule(
            connection,
            summary,
            doctor_id=doctor_id,
            facility_id=facility_id,
            work_date=work_date,
            shift=shift,
            start_at=start_at,
            end_at=end_at,
        )
        ensure_slots(
            connection,
            summary,
            schedule_id=schedule_id,
            doctor_id=doctor_id,
            work_date=work_date,
            start_at=start_at,
            end_at=end_at,
            slot_minutes=slot_minutes,
        )


def print_import_summary(connection: sqlite3.Connection, summary: ImportSummary) -> None:
    print("Import completed.")
    print(f"- facilities_created: {summary.facilities_created}")
    print(f"- facilities_updated: {summary.facilities_updated}")
    print(f"- specialties_created: {summary.specialties_created}")
    print(f"- specialties_updated: {summary.specialties_updated}")
    print(f"- specialties_extended: {summary.specialties_extended}")
    print(f"- doctors_created: {summary.doctors_created}")
    print(f"- doctors_updated: {summary.doctors_updated}")
    print(f"- doctor_specialties_linked: {summary.doctor_specialties_linked}")
    print(f"- schedules_created: {summary.schedules_created}")
    print(f"- schedules_updated: {summary.schedules_updated}")
    print(f"- slots_created: {summary.slots_created}")
    print(f"- slots_skipped: {summary.slots_skipped}")
    print(f"- ambiguous_schedule_names: {summary.ambiguous_schedule_names}")
    print(f"- schedule_rows_skipped: {summary.schedule_rows_skipped}")

    table_names = (
        "facilities",
        "specialties",
        "doctors",
        "doctor_specialties",
        "doctor_schedules",
        "doctor_schedule_slots",
        "users",
        "appointments",
    )
    for table_name in table_names:
        count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"- {table_name}: {count}")


def main() -> None:
    args = parse_args()
    connection = ensure_database_ready(args.db.resolve())
    summary = ImportSummary()

    try:
        with connection:
            facility_key_to_id = import_facilities(
                connection,
                summary,
                args.facilities.resolve(),
                args.google_api_key.strip(),
            )
            specialty_lookup = import_specialties(connection, summary, args.specialties.resolve())
            doctor_name_candidates = import_doctors(
                connection,
                summary,
                args.doctors.resolve(),
                facility_key_to_id,
                specialty_lookup,
                args.google_api_key.strip(),
            )
            import_schedules(
                connection,
                summary,
                args.schedules.resolve(),
                doctor_name_candidates,
                args.slot_minutes,
            )

        print_import_summary(connection, summary)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
