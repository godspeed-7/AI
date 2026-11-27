"""Loads the 12 HR tables (ams-data/db/*.csv) into the agent's database.

In:  uv run python load_data.py; or build(path) (the eval runner).
Out: data/hr.sqlite (rebuilt each time), one table per CSV with the
     same columns, plus `holidays` (office, holiday_date, name) from the
     Employee Handbook's calendar (chapter 6); prints each row count.

Strategy: each column's type comes from its values: all whole numbers
-> INTEGER, all numbers -> REAL, otherwise TEXT; an empty cell is NULL.
A number with a leading zero ("007") stays text. The CSVs stay the
source of truth: this database is rebuilt from them, never edited.

The holidays exist only as tables in the handbook text, so they are
read from there once, into data code can count leave days with (walk
9). One rule is kept by the database itself: a person can't have two
pending or approved requests for the same leave and dates (a partial
unique index, walk 10), so a repeat is refused even if code misses it.

Caveats: no foreign keys (1,200 people is small). Restricted holidays
(India, 2 chosen per person) are not company holidays: not loaded.
"""

import csv
import re
import sqlite3
from contextlib import closing
from datetime import datetime

from ams_agent.config import CSV_DIR, DB_PATH, HANDBOOK, HOLIDAY_SECTIONS

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


HOLIDAY_ROW = re.compile(r"(.+?) \| (\d{1,2} \w+ \d{4}) \| \w+")
SECTION = re.compile(r"\d+(\.\d+)+ ")


def holidays() -> list[tuple[str, str, str]]:
    """(office, ISO date, name) from each office's fixed-holiday table."""
    lines = HANDBOOK.read_text(encoding="utf-8").splitlines()
    found = []
    for office, section in HOLIDAY_SECTIONS.items():
        start = next(i for i, line in enumerate(lines)
                     if line.startswith(f"{section} "))
        for line in lines[start + 1:]:
            if SECTION.match(line):
                break  # the next section
            if match := HOLIDAY_ROW.fullmatch(line.strip()):
                day = datetime.strptime(match[2], "%d %B %Y").date()
                found.append((office, day.isoformat(), match[1]))
    return found


def build(target) -> None:
    """Every table into a new database at `target`, swapped in at the end."""
    target.parent.mkdir(exist_ok=True)
    fresh = target.with_suffix(".building")
    fresh.unlink(missing_ok=True)
    with closing(sqlite3.connect(fresh)) as con:
        for path in sorted(CSV_DIR.glob("*.csv")):
            print(f"{path.stem:22} {load_table(con, path):6,} rows")
        rows = holidays()
        con.execute("CREATE TABLE holidays"
                    " (office TEXT, holiday_date TEXT, name TEXT)")
        con.executemany("INSERT INTO holidays VALUES (?, ?, ?)", rows)
        print(f"{'holidays':22} {len(rows):6,} rows")
        con.execute(
            "CREATE UNIQUE INDEX one_request_per_leave ON leave_requests"
            " (employee_id, leave_type, start_date, end_date)"
            " WHERE status IN ('pending', 'approved')")
        con.commit()
    fresh.replace(target)  # swap in only once every table loaded
    print(f"-> {target}")


def main() -> None:
    build(DB_PATH)


if __name__ == "__main__":
    main()
