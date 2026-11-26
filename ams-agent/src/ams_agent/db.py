"""Opens the agent's HR database, read-only.

In:  DB_PATH (config.py), built by load_data.py.
Out: connect() -> a connection whose rows read like dicts;
     find_employee(id) -> the sign-in screen's lookup;
     count_reports(id) -> direct reports, for the manager role;
     count_rows(table) -> for the evals' database checks.

Strategy: the database is opened with mode=ro, so no tool can change
data, even by mistake (least privilege). Values always go in as ?
parameters, never pasted into the SQL (parameterised queries); a table
name can't be a parameter, so count_rows checks it against the real
tables first (an allowlist).
"""

import sqlite3
from contextlib import closing

from ams_agent.config import DB_PATH


def connect() -> sqlite3.Connection:
    """A read-only connection; rows can be read by column name."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} is missing: run `uv run python load_data.py`.")
    con = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def find_employee(employee_id: str) -> dict | None:
    """Name, office, department, grade and title for an ID, or None."""
    with closing(connect()) as con:
        row = con.execute(
            "SELECT employee_id, name, office, department, grade, job_title"
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
