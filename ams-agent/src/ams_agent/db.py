"""Opens the agent's HR database, read-only, plus the lookups code needs.

In:  config.DB_PATH, built by load_data.py.
Out: connect() (read-only; write=True for the booking only) and lookups:
     find_employee, managers_above, people_named, count_rows, ...

How: mode=ro so no tool can change data; values always go in as ?
parameters, never pasted into the SQL.
"""

import sqlite3
from contextlib import closing

from ams_agent import config


def connect(write: bool = False) -> sqlite3.Connection:
    """A read-only connection; rows can be read by column name.
    write=True is for the leave booking only (leave_booking.py)."""
    path = config.DB_PATH  # read each time: the eval runner points it
    if not path.exists():  # at its own copy
        raise FileNotFoundError(
            f"{path} is missing: run `uv run python load_data.py`.")
    mode = "rw" if write else "ro"
    con = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True,
                          timeout=config.SQLITE_WAIT)
    con.row_factory = sqlite3.Row
    return con


def find_employee(employee_id: str) -> dict | None:
    """An ID's employment record (name, job, grade, office, join date,
    status with its dates, manager), or None."""
    with closing(connect()) as con:
        row = con.execute(
            "SELECT employee_id, name, office, department, grade, job_title,"
            " join_date, status, probation_end_date, resignation_date,"
            " last_working_day, manager_id"
            " FROM employees WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
    return dict(row) if row else None


def count_reports(employee_id: str) -> int:
    """How many people have this person as their manager."""
    with closing(connect()) as con:
        return con.execute(
            "SELECT COUNT(*) FROM employees WHERE manager_id = ?",
            (employee_id,),
        ).fetchone()[0]


def count_rows(table: str) -> int:
    """How many rows a table has; only real table names are accepted."""
    with closing(connect()) as con:
        tables = {name for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        if table not in tables:
            raise ValueError(f"no table named {table!r}")
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def managers_above(employee_id: str) -> set[str]:
    """Everyone above this person: their manager, that manager's..."""
    with closing(connect()) as con:
        rows = con.execute(
            "WITH RECURSIVE up(id) AS ("
            " SELECT manager_id FROM employees WHERE employee_id = ?"
            " UNION SELECT e.manager_id FROM employees e JOIN up"
            " ON e.employee_id = up.id WHERE e.manager_id IS NOT NULL)"
            " SELECT id FROM up WHERE id IS NOT NULL",
            (employee_id,),
        ).fetchall()
    return {r[0] for r in rows}


def people_named(name: str) -> list[str]:
    """IDs whose full, first or last name is `name` (any case)."""
    with closing(connect()) as con:
        rows = con.execute(
            "SELECT employee_id FROM employees WHERE lower(name) = lower(?)"
            " OR lower(substr(name, 1, instr(name, ' ') - 1)) = lower(?)"
            " OR lower(substr(name, instr(name, ' ') + 1)) = lower(?)"
            " ORDER BY employee_id",
            (name, name, name),
        ).fetchall()
    return [r[0] for r in rows]


def direct_reports(employee_id: str) -> list[dict]:
    """The people who report to this person: ID, job, grade, office."""
    with closing(connect()) as con:
        rows = con.execute(
            "SELECT employee_id, job_title, grade, office, status"
            " FROM employees WHERE manager_id = ? ORDER BY employee_id",
            (employee_id,),
        ).fetchall()
    return [dict(r) for r in rows]
