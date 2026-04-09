from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "vinmec.sqlite3"
BRANCHES_CSV = BASE_DIR / "danh_sach_co_so.csv"
DOCTORS_CSV = BASE_DIR / "danh_sach_bac_si.csv"
SPECIALTY_CSV = BASE_DIR / "chuyen_khoa.csv"

BRANCH_COORDINATES: dict[str, tuple[float, float]] = {
    "benh vien da khoa quoc te vinmec times city": (20.9938194, 105.8671963),
    "benh vien da khoa vinmec smart city": (21.0079133, 105.7471695),
    "benh vien da khoa quoc te vinmec central park": (10.7940524, 106.7203681),
    "benh vien da khoa vinmec ha long": (20.9520499, 107.0719397),
    "benh vien da khoa vinmec hai phong": (20.8232825, 106.6879856),
    "benh vien da khoa vinmec nha trang": (12.2126502, 109.2107161),
    "benh vien da khoa vinmec phu quoc": (10.3366819, 103.8566615),
    "benh vien da khoa vinmec da nang": (16.0387756, 108.2112996),
    "benh vien da khoa vinmec can tho": (10.0260810, 105.7699584),
    "benh vien da khoa quoc te vinmec ocean park 2": (20.9396981, 105.9899806),
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("đ", "d").replace("Đ", "d")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def to_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def get_branch_coordinates(branch_name: str) -> tuple[float, float]:
    normalized_name = normalize_text(branch_name)
    coordinates = BRANCH_COORDINATES.get(normalized_name)
    if coordinates is None:
        raise ValueError(f"Missing coordinates for branch: {branch_name}")
    return coordinates


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.executescript(
        """
        DROP TABLE IF EXISTS doctors;
        DROP TABLE IF EXISTS branch_coordinates;
        DROP TABLE IF EXISTS branches;
        DROP TABLE IF EXISTS specialty;

        CREATE TABLE branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            address TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL
        );

        CREATE TABLE specialty (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            degrees TEXT,
            description TEXT,
            speciality TEXT,
            qualification TEXT,
            vinmec_site TEXT,
            price_local INTEGER,
            price_foreigner INTEGER,
            branch_id INTEGER,
            specialty_id INTEGER,
            FOREIGN KEY(branch_id) REFERENCES branches(id),
            FOREIGN KEY(specialty_id) REFERENCES specialty(id)
        );
        """
    )


def best_branch_match(site_name: str | None, branch_rows: list[dict[str, str]]) -> int | None:
    if not site_name:
        return None

    normalized_site = normalize_text(site_name)
    if not normalized_site:
        return None

    exact_matches: list[tuple[int, int]] = []
    partial_matches: list[tuple[int, int]] = []

    for index, row in enumerate(branch_rows):
        normalized_branch = normalize_text(row["name"])
        if not normalized_branch:
            continue
        if normalized_site == normalized_branch:
            exact_matches.append((len(normalized_branch), index))
            continue
        if normalized_site in normalized_branch or normalized_branch in normalized_site:
            partial_matches.append((len(normalized_branch), index))

    if exact_matches:
        return branch_rows[min(exact_matches)[1]]["id"]
    if partial_matches:
        return branch_rows[min(partial_matches)[1]]["id"]

    site_tokens = set(normalized_site.split())
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(branch_rows):
        normalized_branch = normalize_text(row["name"])
        branch_tokens = set(normalized_branch.split())
        score = len(site_tokens & branch_tokens)
        if score > best_score:
            best_score = score
            best_index = index

    if best_index is None or best_score == 0:
        return None
    return branch_rows[best_index]["id"]


def build_specialty_lookup(specialty_rows: list[dict[str, str]]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for row in specialty_rows:
        lookup[normalize_text(row["name"])] = int(row["id"])
    return lookup


def best_specialty_match(raw_speciality: str | None, specialty_lookup: dict[str, int]) -> int | None:
    if not raw_speciality:
        return None

    specialty_parts = [part.strip() for part in raw_speciality.split(",") if part.strip()]
    if not specialty_parts:
        specialty_parts = [raw_speciality.strip()]

    alias_map = {
        "can thiep tim mach": "noi tim mach",
        "co xuong khop": "ngoai chan thuong chinh hinh",
        "hoi suc cap cuu": "da khoa",
        "khoa phu": "san phu khoa",
        "khoa san": "san phu khoa",
        "khoa vu": "trung tam benh ly vu",
        "khoa y hoc bao thai": "san phu khoa",
        "mien dich di ung": "hen di ung mien dich",
        "ngoai tim mach": "ngoai chan thuong chinh hinh",
        "ngoai tieu hoa": "noi tieu hoa",
        "noi tong quat": "da khoa",
        "phau thuat tim mach long nguc": "ngoai chan thuong chinh hinh",
        "phau thuat u xuong va phan mem": "ngoai chan thuong chinh hinh",
        "phau thuat chi duoi": "ngoai chan thuong chinh hinh",
        "phau thuat chi tren": "ngoai chan thuong chinh hinh",
        "phau thuat noi soi khop va yhtt": "ngoai chan thuong chinh hinh",
        "san khoa": "san phu khoa",
        "ung buou xa tri": "trung tam ung buou",
        "ung buou x a tri": "trung tam ung buou",
        "ung buou xatr i": "trung tam ung buou",
        "vaccine": "tiem chung vac xin",
        "y hoc co truyen": "da khoa",
    }

    normalized_lookup_keys = list(specialty_lookup.keys())
    ordered_keyword_matches = [
        "benh ly tuyen giap",
        "noi tiet",
        "da lieu",
        "dinh duong",
        "di truyen y hoc",
        "gay me",
        "di ung mien dich nhi",
        "di ung mien dich",
        "hen di ung mien dich nhi",
        "hen di ung mien dich",
        "ho hap",
        "ho tro sinh san",
        "huyet hoc",
        "mat",
        "nam khoa",
        "ngoai chan thuong chinh hinh",
        "ngoai nhi",
        "ngoai than kinh",
        "ngoai than tiet nieu",
        "noi tieu hoa",
        "noi tim mach",
        "san phu khoa",
        "tai mui hong nhi",
        "tai mui hong",
        "tam ly",
        "tam than",
        "tham my",
        "tiem chung vac xin",
        "truyen nhiem",
        "y hoc giac ngu",
    ]

    for part in specialty_parts:
        normalized_part = normalize_text(part)
        alias_target = alias_map.get(normalized_part)
        if alias_target:
            for key in normalized_lookup_keys:
                if alias_target in key:
                    return specialty_lookup[key]

        if normalized_part in specialty_lookup:
            return specialty_lookup[normalized_part]

        for key in normalized_lookup_keys:
            if normalized_part == key or normalized_part in key or key in normalized_part:
                return specialty_lookup[key]

        for keyword in ordered_keyword_matches:
            if keyword in normalized_part:
                for key in normalized_lookup_keys:
                    if keyword in key:
                        return specialty_lookup[key]

    return None


def insert_branches(connection: sqlite3.Connection, branch_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows_with_ids: list[dict[str, str]] = []
    for row in branch_rows:
        branch_name = row["name"].strip()
        branch_address = row.get("address", "").strip() or None
        latitude, longitude = get_branch_coordinates(branch_name)
        cursor = connection.execute(
            "INSERT INTO branches (name, address, latitude, longitude) VALUES (?, ?, ?, ?)",
            (branch_name, branch_address, latitude, longitude),
        )
        rows_with_ids.append({"id": cursor.lastrowid, "name": branch_name})
    return rows_with_ids


def insert_specialty(connection: sqlite3.Connection, specialty_rows: list[dict[str, str]]) -> None:
    for row in specialty_rows:
        connection.execute(
            "INSERT INTO specialty (id, name) VALUES (?, ?)",
            (int(row["id"]), row["name"].strip()),
        )


def insert_doctors(
    connection: sqlite3.Connection,
    doctor_rows: list[dict[str, str]],
    branch_rows: list[dict[str, str]],
    specialty_lookup: dict[str, int],
) -> None:
    for row in doctor_rows:
        branch_id = best_branch_match(row.get("vinmec_site"), branch_rows)
        specialty_id = best_specialty_match(row.get("speciality"), specialty_lookup)

        connection.execute(
            """
            INSERT INTO doctors (
                name, degrees, description, speciality, qualification,
                vinmec_site, price_local, price_foreigner, branch_id, specialty_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (row.get("name") or "").strip(),
                (row.get("degrees") or "").strip() or None,
                (row.get("description") or "").strip() or None,
                (row.get("speciality") or "").strip() or None,
                (row.get("qualification") or "").strip() or None,
                (row.get("vinmec_site") or "").strip() or None,
                to_int(row.get("price_local")),
                to_int(row.get("price_foreigner")),
                branch_id,
                specialty_id,
            ),
        )


def build_database(output_path: Path) -> None:
    branch_rows = read_csv(BRANCHES_CSV)
    specialty_rows = read_csv(SPECIALTY_CSV)
    doctor_rows = read_csv(DOCTORS_CSV)

    with sqlite3.connect(output_path) as connection:
        create_schema(connection)
        inserted_branch_rows = insert_branches(connection, branch_rows)
        insert_specialty(connection, specialty_rows)
        specialty_lookup = build_specialty_lookup(specialty_rows)
        insert_doctors(connection, doctor_rows, inserted_branch_rows, specialty_lookup)
        connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a SQLite database from the Vinmec CSV files.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="SQLite output path")
    args = parser.parse_args()

    build_database(args.output)
    print(f"SQLite database created at: {args.output}")


if __name__ == "__main__":
    main()