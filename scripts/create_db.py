from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "vinmec.sqlite"
DEFAULT_SCHEMA_PATH = ROOT_DIR / "database" / "schema.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the SQLite database schema.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to the SQLite database file.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH, help="Path to the schema.sql file.")
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    db_path = args.db.resolve()
    schema_path = args.schema.resolve()

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")

    connection = sqlite3.connect(db_path)
    try:
        configure_connection(connection, db_path)
        connection.executescript(schema_sql)
        connection.commit()
    finally:
        connection.close()

    print(f"Database schema created at: {db_path}")


if __name__ == "__main__":
    main()
