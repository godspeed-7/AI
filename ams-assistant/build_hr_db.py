"""Build the HR database: ams-data/db/*.csv -> one SQLite file.

In:  employees.csv, leave_balances.csv, leave_requests.csv and
     expense_claims.csv in HR_DATA_DIR (ams-data/db/).
Out: HR_DB_FILE (.cache/hr.sqlite): one table per CSV, same columns.

Strategy: delete the old file and copy every row in again, so each run
gives a fresh copy of the CSVs (once the agent can write, this is the
reset). Plain sqlite3 from Python's standard library; no LangChain.

Caveats:
- Day, amount and year columns are numbers (NUMBER_COLUMNS), so SQL
  can add them up; everything else is text. Dates stay "YYYY-MM-DD"
  text, which sorts and compares correctly. Empty cells become NULL.
- The CSVs are the source of truth: change them (ams-data/db/
  build_hr_data.py), then re-run this script.
"""

import csv
import sqlite3

from ams_assistant.config import HR_DATA_DIR, HR_DB_FILE

# One table per CSV file, named after it.
TABLES = ["employees", "leave_balances", "leave_requests",
          "expense_claims"]

# Columns stored as numbers; every other column is TEXT.
NUMBER_COLUMNS = {
    "leave_year": "INTEGER",
    "entitled_days": "REAL",
    "carried_over_days": "REAL",
    "used_days": "REAL",
    "pending_days": "REAL",
    "days": "REAL",  # leave requests: 0.5 for a half day
    "nights": "INTEGER",
    "amount": "REAL",
}


def copy_csv(db: sqlite3.Connection, table: str) -> int:
    """Create `table` with the CSV's columns, insert every row, and
    return the row count."""
    with open(HR_DATA_DIR / f"{table}.csv", newline="",
              encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
        # "" (an empty cell) -> None, which SQLite stores as NULL.
        rows = [{k: v or None for k, v in row.items()} for row in reader]

    column_types = ", ".join(
        f"{name} {NUMBER_COLUMNS.get(name, 'TEXT')}" for name in columns)
    db.execute(f"CREATE TABLE {table} ({column_types})")

    # :name placeholders take the values from each row dict by column
    # name. A REAL or INTEGER column turns the CSV's text ("20.0") into
    # a number as it's stored.
    placeholders = ", ".join(f":{name}" for name in columns)
    db.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
    return len(rows)


def main():
    HR_DB_FILE.parent.mkdir(exist_ok=True)
    HR_DB_FILE.unlink(missing_ok=True)  # start from an empty file

    db = sqlite3.connect(HR_DB_FILE)
    try:
        for table in TABLES:
            print(f"  {table}: {copy_csv(db, table)} rows")
        db.commit()
    finally:
        db.close()
    print(f"Wrote {HR_DB_FILE}")


if __name__ == "__main__":
    main()
