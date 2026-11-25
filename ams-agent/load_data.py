"""Loads the 12 HR tables (ams-data/db/*.csv) into the agent's database.

In:  uv run python load_data.py
Out: data/hr.sqlite (rebuilt each time), one table per CSV with the
     same columns; prints each table's row count.

Strategy: each column's type comes from its values: all whole numbers
-> INTEGER, all numbers -> REAL, otherwise TEXT; an empty cell is NULL.
A number with a leading zero ("007") stays text. The CSVs stay the
source of truth: this database is rebuilt from them, never edited.

Caveats: no indexes or foreign keys yet (1,200 people is small).
"""

import csv
import re
import sqlite3
from contextlib import closing

from ams_agent.config import CSV_DIR, DB_PATH

WHOLE = re.compile(r"-?(0|[1-9]\d*)")
DECIMAL = re.compile(r"-?(0|[1-9]\d*)\.\d+")


def column_type(values: list[str]) -> str:
    """INTEGER, REAL or TEXT, from a column's non-empty values."""
    filled = [v for v in values if v != ""]
    if filled and all(WHOLE.fullmatch(v) for v in filled):
        return "INTEGER"
    if filled and all(WHOLE.fullmatch(v) or DECIMAL.fullmatch(v)
                      for v in filled):
        return "REAL"
    return "TEXT"


def convert(value: str, kind: str) -> int | float | str | None:
    if value == "":
        return None
    return {"INTEGER": int, "REAL": float}.get(kind, str)(value)


def load_table(con: sqlite3.Connection, path) -> int:
    """One CSV -> one table named after the file; returns its row count."""
    with path.open(newline="", encoding="utf-8") as f:
        header, *rows = list(csv.reader(f))
    kinds = [column_type([row[i] for row in rows])
             for i in range(len(header))]
    columns = ", ".join(f'"{name}" {kind}'
                        for name, kind in zip(header, kinds))
    con.execute(f'CREATE TABLE "{path.stem}" ({columns})')
    marks = ", ".join("?" * len(header))
    con.executemany(
        f'INSERT INTO "{path.stem}" VALUES ({marks})',
        ([convert(v, k) for v, k in zip(row, kinds)] for row in rows))
    return len(rows)


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    fresh = DB_PATH.with_suffix(".building")
    fresh.unlink(missing_ok=True)
    with closing(sqlite3.connect(fresh)) as con:
        for path in sorted(CSV_DIR.glob("*.csv")):
            print(f"{path.stem:22} {load_table(con, path):6,} rows")
        con.commit()
    fresh.replace(DB_PATH)  # swap in only once every table loaded
    print(f"-> {DB_PATH}")


if __name__ == "__main__":
    main()
