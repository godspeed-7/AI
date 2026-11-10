"""HR tools: what the agent can look up in the HR database.

In:  the logged-in employee's ID (from our code) + the inputs the model
     fills in, e.g. get_my_leave_balance(leave_type="annual").
Out: a dict of facts; the model writes the sentence.

Strategy: each tool is a plain function made into a LangChain tool by
@tool. The model never sees the code, only the tool's name, docstring
and the inputs it may fill in. The employee ID is an InjectedToolArg:
left out of what the model sees and added by our code, so the model
can't ask for anyone else's data.

Caveats:
- Reads HR_DB_FILE; build it first with build_hr_db.py.
- Sums ("available") are done in SQL, not left to the model.
- The data holds leave year 2026 only (as of 16 Nov 2026).
- get_employee_name() is a plain helper for the app, not a tool.
"""

import sqlite3
from contextlib import closing
from typing import Annotated, Literal

from langchain_core.tools import InjectedToolArg, tool

from ams_assistant.config import HR_DB_FILE

# Available = entitled + carried over - used - pending; the CSVs don't
# store it, so it can't go out of sync.
BALANCE_SQL = """
    SELECT leave_type,
           entitled_days,
           carried_over_days,
           used_days,
           pending_days,
           entitled_days + carried_over_days - used_days - pending_days
               AS available_days
    FROM leave_balances
    WHERE employee_id = ?
"""


def connect() -> sqlite3.Connection:
    """Open HR_DB_FILE read-only; rows can be turned into dicts."""
    # mode=ro: the tools can't change the data, and a missing file is
    # an error instead of a new, empty database.
    db = sqlite3.connect(f"{HR_DB_FILE.as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row  # dict(row) -> {column: value}
    return db


def get_employee_name(employee_id: str) -> str:
    """The employee's name, for the agent's instructions. Raises
    ValueError for an unknown ID."""
    with closing(connect()) as db:
        row = db.execute("SELECT name FROM employees WHERE employee_id = ?",
                         (employee_id,)).fetchone()
    if row is None:
        raise ValueError(f"No employee with ID {employee_id}")
    return row["name"]


@tool(parse_docstring=True)
def get_my_leave_balance(
    employee_id: Annotated[str, InjectedToolArg],
    leave_type: Literal["annual", "sick", "casual", "pto",
                        "floating"] | None = None,
) -> dict:
    """Get this year's leave balance of the employee you are helping.

    Returns one entry per leave type: days entitled, carried over from
    last year, used, pending approval, and available now.

    Args:
        employee_id: Added by the app, never by the model.
        leave_type: Only this type of leave. India offices have annual,
            sick and casual leave; the US office has pto, sick and
            floating. Leave it out to get every type.
    """
    # closing(): sqlite3's own `with` doesn't close the connection.
    with closing(connect()) as db:
        rows = [dict(row) for row in db.execute(BALANCE_SQL,
                                                (employee_id,))]

    # Problems go back to the model as a message it can act on, not as
    # an exception that ends the run.
    if not rows:
        return {"error": f"No leave balance found for {employee_id}."}
    if leave_type:
        rows = [row for row in rows if row["leave_type"] == leave_type]
        if not rows:
            return {"error": f"There is no {leave_type} leave for this "
                             "employee; leave it out to see every type."}
    return {"balances": rows}
