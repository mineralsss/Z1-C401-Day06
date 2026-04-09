import sqlite3
import sys

DB_PATH = "data/vinmec.sqlite"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"\n=== Database: {DB_PATH} ===")
print("Tables:", [t[0] for t in tables])

table_name = sys.argv[1] if len(sys.argv) > 1 else None

if table_name:
    rows = conn.execute(f"SELECT * FROM {table_name} LIMIT 20").fetchall()
    if rows:
        print(f"\n--- {table_name} ({len(rows)} rows) ---")
        print(" | ".join(rows[0].keys()))
        print("-" * 80)
        for row in rows:
            print(" | ".join(str(v) for v in row))
    else:
        print(f"Bảng {table_name} trống.")
else:
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
        print(f"  {t[0]}: {count} rows")
