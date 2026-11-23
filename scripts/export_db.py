"""Export every table of the Saathi SQLite database to CSV (and print row counts), so it can be read without a DB tool.

    python scripts/export_db.py                       # reads data/saathi.db, writes exports/*.csv
    python scripts/export_db.py path/to/other.db

Reads a COPY of the database, so it is safe while the backend is running. Session payloads (full transcripts, raw member
messages) are exported as JSON text: treat the exports folder as sensitive and do not commit it (it is git-ignored).
"""
import csv
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "data/saathi.db")
    if not src.exists():
        sys.exit(f"{src} not found. Start the backend once (it creates the database), then run this again.")
    out = Path("exports")
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.db"
        live = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)  # consistent snapshot incl. the WAL
        snap = sqlite3.connect(copy)
        live.backup(snap)
        live.close()
        db = snap
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            cur = db.execute(f"SELECT * FROM {table}")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            with open(out / f"{table}.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            print(f"{table:10s} {len(rows):5d} rows -> exports/{table}.csv")
        snap.close()


if __name__ == "__main__":
    main()
