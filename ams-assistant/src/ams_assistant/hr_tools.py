"""HR tools: what the agent can look up in the HR database.

In:  who is asking (HRContext, set by our code) + the inputs the model
     fills in, e.g. get_leave_balance(leave_type="annual").
Out: a dict of facts; the model writes the sentence.

Strategy: each tool is a plain function made into a LangChain tool by
@tool. The model never sees the code, only the tool's name, docstring
and the inputs it may fill in. A `runtime` argument is left out of
what the model sees and filled by the agent with who is asking
(runtime.context), never from the chat. The model may name another
employee (`employee`); permissions.py decides what the asker may see
about them before anything is read. Each result names whose records
it holds ("employee"), so the model can't present them as someone
else's.

Caveats:
- Reads HR_DB_FILE; build it first with build_hr_db.py.
- Sums ("available") are done in SQL, not left to the model; empty
  (NULL) columns are left out of results.
- The data holds leave year 2026 only, as of TODAY (16 Nov 2026);
  date maths (time at AMS) counts to TODAY, not the real clock.
- get_employee_name() and get_employee_card() are plain helpers for
  the app, not tools.
"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from typing import Literal

from langchain.tools import ToolRuntime, tool

from ams_assistant.config import HR_DB_FILE, TODAY
from ams_assistant.permissions import (
    NOT_ALLOWED,
    Access,
    access,
    manager_view,
    may_read,
)


@dataclass
class HRContext:
    """Who the agent is helping. Our code sets it for each run (like
    a login would); the model can't see or change it."""

    employee_id: str


# Payroll isn't stored: Bengaluru and Pune are India payroll, Austin is
# US payroll. No email: the agent doesn't need contact details.
PROFILE_SQL = """
    SELECT e.employee_id, e.name, e.office,
           CASE WHEN e.office = 'Austin' THEN 'US' ELSE 'India' END
               AS payroll,
           e.department, e.grade, e.job_title,
           m.name AS manager_name,
           e.join_date, e.status, e.probation_end_date,
           e.resignation_date, e.last_working_day
    FROM employees AS e
    LEFT JOIN employees AS m ON m.employee_id = e.manager_id
    WHERE e.employee_id = ?
"""

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

# The approver's name instead of their ID, so the model can say who.
REQUESTS_SQL = """
    SELECT r.request_id, r.leave_type, r.start_date, r.end_date,
           r.days AS working_days, r.status, r.submitted_on,
           a.name AS approver_name
    FROM leave_requests AS r
    LEFT JOIN employees AS a ON a.employee_id = r.approver_id
    WHERE r.employee_id = ?
    ORDER BY r.start_date
"""

# Direct reports only (not their teams in turn): who they are and the
# dates of their status, no leave or expenses of other people. The
# probation end date only while on probation (NULL otherwise, and
# fetch() drops it); the last working day is only set when leaving.
TEAM_SQL = """
    SELECT employee_id, name, job_title, office, status,
           CASE WHEN status = 'probation' THEN probation_end_date END
               AS probation_end_date,
           last_working_day
    FROM employees
    WHERE manager_id = ?
    ORDER BY name
"""

# Who `employee` may mean: an ID, a full name or a first name, in any
# case. permissions.py then decides which of them the asker may see.
# :first_name is "<q> %" with q's own % and _ escaped (ESCAPE '\'), so
# only the trailing % is a wildcard: "%" or "K%" match no one.
FIND_SQL = r"""
    SELECT employee_id, name, manager_id
    FROM employees
    WHERE lower(employee_id) = :q OR lower(name) = :q
       OR lower(name) LIKE :first_name ESCAPE '\'
"""

CLAIMS_SQL = """
    SELECT c.claim_id, c.trip_id, c.category, c.description, c.city,
           c.nights, c.amount, c.currency, c.expense_date,
           c.submitted_on, c.receipt_attached,
           c.lost_receipt_declaration, c.status,
           a.name AS approver_name
    FROM expense_claims AS c
    LEFT JOIN employees AS a ON a.employee_id = c.approver_id
    WHERE c.employee_id = ?
    ORDER BY c.expense_date
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


def fetch(sql: str, employee_id: str) -> list[dict]:
    """Run one of the queries above for `employee_id`: one dict per row,
    without its empty (NULL) columns."""
    # closing(): sqlite3's own `with` doesn't close the connection.
    with closing(connect()) as db:
        rows = db.execute(sql, (employee_id,)).fetchall()
    return [{column: value for column, value in dict(row).items()
             if value is not None} for row in rows]


def whose(employee_id: str) -> str:
    """Whose records a tool returns, e.g. 'Rahul Verma (AMS-1014)'.
    Asked "How many leaves does Ananya have?", the model once got
    Rahul's balance and wrote it up as Ananya's; with his name next to
    the numbers, that mistake is plain to see."""
    return f"{get_employee_name(employee_id)} ({employee_id})"


def find_employee(runtime: ToolRuntime[HRContext], employee: str | None,
                  record: str) -> tuple[str, Access] | None:
    """Who `employee` means (an ID, full name or first name, as the
    model wrote it; empty = the person asking) and the asker's access
    to them, if that access may read `record`; else None. "Not found"
    and "not allowed" both give None (permissions.py)."""
    viewer_id = runtime.context.employee_id
    if not employee or not employee.strip():
        matches = [(viewer_id, "self")]
    else:
        q = employee.strip().lower()
        # LIKE's wildcards (% and _) in the name become plain text.
        escaped = (q.replace("\\", "\\\\").replace("%", "\\%")
                   .replace("_", "\\_"))
        with closing(connect()) as db:
            rows = db.execute(FIND_SQL, {"q": q,
                                         "first_name": f"{escaped} %"}
                              ).fetchall()
        # Only the people the asker may see count as matches.
        matches = [(row["employee_id"], level) for row in rows
                   if (level := access(viewer_id, dict(row)))]
    # Two such people with one first name: refuse rather than guess
    # (no such pair in our data).
    if len(matches) != 1 or not may_read(matches[0][1], record):
        return None
    return matches[0]


def get_employee_card(employee_id: str) -> dict | None:
    """The employee's profile plus how many people report to them, for
    the app's sign-in card; None for an unknown ID."""
    rows = fetch(PROFILE_SQL, employee_id)
    if not rows:
        return None
    card = rows[0]
    card["direct_reports"] = fetch(
        "SELECT COUNT(*) AS n FROM employees WHERE manager_id = ?",
        employee_id)[0]["n"]
    return card


def time_since(start: str, end: date = TODAY) -> str:
    """Whole years and months from a 'YYYY-MM-DD' date to `end`:
    '2016-03-01' -> '10 years 8 months'."""
    begin = date.fromisoformat(start)
    months = (end.year - begin.year) * 12 + end.month - begin.month
    if end.day < begin.day:  # the last month isn't complete yet
        months -= 1
    years, months = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months or not years:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts)


@tool(parse_docstring=True)
def get_profile(runtime: ToolRuntime[HRContext],
                employee: str | None = None) -> dict:
    """Get an employee's profile: by default, the employee you are
    helping.

    Returns their name and employee ID, office and payroll country
    (India or US), department, grade (L1 to L6), job title, manager,
    join date, time at AMS (how long they have worked here: their
    experience at AMS), and employment status: probation (in the US,
    the 90-day introductory period) with its end date, confirmed, or
    notice_period with the resignation date and last working day.

    Args:
        runtime: Added by the agent, never by the model.
        employee: Whose profile, when the question is about someone
            else: their name or employee ID. Leave it out for the
            employee you are helping.
    """
    found = find_employee(runtime, employee, "profile")
    if found is None:
        return NOT_ALLOWED
    employee_id, level = found
    rows = fetch(PROFILE_SQL, employee_id)
    if not rows:
        return {"error": "No profile found for this employee."}
    if level == "manager":
        return manager_view(rows[0])
    profile = rows[0]
    # Code does the date maths, not the model.
    profile["time_at_ams"] = time_since(profile["join_date"])
    return profile


@tool(parse_docstring=True)
def get_my_team(runtime: ToolRuntime[HRContext]) -> dict:
    """List the people who report directly to the employee you are
    helping (their team).

    Returns how many direct reports they have, and each one's name,
    employee ID, job title, office and status: probation (with its end
    date), confirmed, or notice_period (with the last working day).
    Empty if no one reports to them.

    Args:
        runtime: Added by the agent, never by the model.
    """
    employee_id = runtime.context.employee_id
    team = fetch(TEAM_SQL, employee_id)
    # The count comes from code, so the model doesn't have to count.
    return {"employee": whose(employee_id), "direct_reports": len(team),
            "team": team}


@tool(parse_docstring=True)
def get_leave_balance(
    runtime: ToolRuntime[HRContext],
    employee: str | None = None,
    leave_type: Literal["annual", "sick", "casual", "pto",
                        "floating"] | None = None,
) -> dict:
    """Get this year's leave balance of an employee: by default, the
    employee you are helping.

    Returns one entry per leave type: days entitled, carried over from
    last year, used, pending approval, and available now (entitled +
    carried over - used - pending).

    Args:
        runtime: Added by the agent, never by the model.
        employee: Whose balance, when the question is about someone
            else: their name or employee ID. Leave it out for the
            employee you are helping.
        leave_type: Only this type of leave. India offices have annual
            (vacation), sick and casual leave; the US office has pto
            (paid time off, vacation), sick and floating (floating
            holidays). Leave it out to get every type.
    """
    found = find_employee(runtime, employee, "leave")
    if found is None:
        return NOT_ALLOWED
    employee_id = found[0]
    rows = fetch(BALANCE_SQL, employee_id)

    # Problems go back to the model as a message it can act on, not as
    # an exception that ends the run.
    if not rows:
        return {"error": "No leave balance found for this employee."}
    if leave_type:
        rows = [row for row in rows if row["leave_type"] == leave_type]
        if not rows:
            return {"error": f"There is no {leave_type} leave for this "
                             "employee; leave it out to see every type."}
    return {"employee": whose(employee_id), "balances": rows}


# No status filter on the two lists below: given one, the model turned
# "approved?" into status="approved" and filtered the answer away (a
# pending request). The lists are short; the model reads each status.
@tool(parse_docstring=True)
def get_leave_requests(runtime: ToolRuntime[HRContext],
                       employee: str | None = None) -> dict:
    """List all of this year's leave requests of an employee: by
    default, the employee you are helping.

    Returns each request's ID (e.g. LR-0189), leave type, start and end
    dates, working days (weekends and office holidays not counted; 0.5
    is half a day), status (approved, pending, rejected or cancelled),
    the date it was submitted, and who approves it.

    Args:
        runtime: Added by the agent, never by the model.
        employee: Whose requests, when the question is about someone
            else: their name or employee ID. Leave it out for the
            employee you are helping.
    """
    found = find_employee(runtime, employee, "leave")
    if found is None:
        return NOT_ALLOWED
    employee_id = found[0]
    return {"employee": whose(employee_id),
            "leave_requests": fetch(REQUESTS_SQL, employee_id)}


def trip_totals(claims: list[dict]) -> list[dict]:
    """One summary per trip, added up by code: its city, total amount,
    number of items, dates and whether it's paid."""
    trips: dict[str, list[dict]] = {}
    for claim in claims:
        trips.setdefault(claim["trip_id"], []).append(claim)

    summaries = []
    for trip_id, items in trips.items():
        statuses = {item["status"] for item in items}
        if statuses == {"paid"}:
            paid = "paid"
        elif statuses == {"submitted"}:
            paid = "not paid yet"
        else:
            paid = "partly paid"
        dates = sorted(item["expense_date"] for item in items)
        summaries.append({
            "trip_id": trip_id,
            "city": ", ".join(sorted({item["city"] for item in items})),
            "total": round(sum(item["amount"] for item in items), 2),
            "currency": ", ".join(sorted({i["currency"] for i in items})),
            "items": len(items),
            "dates": (dates[0] if dates[0] == dates[-1]
                      else f"{dates[0]} to {dates[-1]}"),
            "status": paid,
        })
    return summaries


@tool(parse_docstring=True)
def get_expense_claims(runtime: ToolRuntime[HRContext],
                       employee: str | None = None) -> dict:
    """List all expense claims of an employee: by default, the employee
    you are helping.

    Returns a summary per trip (city, total amount, number of items,
    dates, paid or not), then each expense item; items with the same
    trip ID make one trip. Each item has its claim ID, trip, category
    (hotel, daily_allowance, taxi or other), description, city, nights
    (hotels), amount and currency, expense date, submitted date,
    whether a receipt is attached or a lost-receipt declaration was
    made, status (submitted = not paid yet, or paid), and who approves
    it.

    Args:
        runtime: Added by the agent, never by the model.
        employee: Whose claims, when the question is about someone
            else: their name or employee ID. Leave it out for the
            employee you are helping.
    """
    found = find_employee(runtime, employee, "expenses")
    if found is None:
        return NOT_ALLOWED
    employee_id = found[0]
    claims = fetch(CLAIMS_SQL, employee_id)
    # Totals come from code, so the model doesn't have to add up.
    return {"employee": whose(employee_id), "trips": trip_totals(claims),
            "expense_claims": claims}
