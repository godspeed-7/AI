"""Year-end review tools: the numbers People Operations needs for each
department (DEEP_AGENTS_PLAYBOOK.md, stage A).

In:  who is asking (HRContext: People Operations only, the "hr" level
     in permissions.py) + a department, e.g. year_end_leave("Sales").
Out: year_end_leave(department), a tool -> per person: their
     carry-over rule, days available, days lost on 31 December and
     days carried into 2027 (to use by when), and their pending
     requests; the department's totals; its head.
     department_review(department): the same, for code.

Strategy: code does every sum and picks each person's rule from their
payroll (Employee Handbook 4.4, India: 5 annual days, use by 31 March;
5.4, US: 10 PTO days, use by 30 June). The model only reads and
writes (stage A: "workflow or agent").

Caveats:
- "Lost" assumes no more leave is taken before 31 December and every
  pending request is approved (available = entitled + carried over -
  used - pending). A rejected request means more days lost.
- Annual leave and PTO only: sick, casual and floating days don't carry
  over either, but aren't planned holiday.
- Someone leaving before 31 December loses nothing that day: their
  unused leave is settled when they leave (4.4.4, 5.4).
- Approved exceptions to the limit (4.4.3) aren't in the data.
"""

from contextlib import closing
from datetime import date
from typing import Literal, get_args

from langchain.tools import ToolRuntime, tool

from ams_assistant.config import TODAY
from ams_assistant.hr_tools import HRContext, connect, fetch, whose
from ams_assistant.permissions import hr_access, may_read

Department = Literal["Engineering", "Delivery", "Sales", "Finance",
                     "People Operations", "IT and Security"]
DEPARTMENTS: tuple[str, ...] = get_args(Department)

YEAR_END = date(TODAY.year, 12, 31)

# Leave type -> (most days carried into next year, the date they must
# be used by, the handbook section). Same as ams-data's build_hr_data.
CARRY_OVER = {
    "annual": (5, date(TODAY.year + 1, 3, 31),
               "Employee Handbook 4.4 (India annual leave)"),
    "pto": (10, date(TODAY.year + 1, 6, 30),
            "Employee Handbook 5.4 (US PTO)"),
}

NOT_HR = {"error": "Not allowed: the year-end review is for People "
                   "Operations only."}

SETTLED_ON_LEAVING = ("leaving before 31 December: unused leave is "
                      "settled on leaving (Employee Handbook 4.4.4, 5.4)")

VIEWER_SQL = "SELECT department FROM employees WHERE employee_id = ?"

HEAD_SQL = """
    SELECT employee_id FROM employees
    WHERE department = ? AND manager_id IS NULL
"""

# One row per person in the department: their annual leave (India) or
# PTO (US) for this year; available worked out in SQL, as in hr_tools.
BALANCES_SQL = """
    SELECT e.employee_id, e.office,
           CASE WHEN e.office = 'Austin' THEN 'US' ELSE 'India' END
               AS payroll,
           e.status, e.last_working_day,
           b.leave_type, b.entitled_days, b.carried_over_days,
           b.used_days, b.pending_days,
           b.entitled_days + b.carried_over_days - b.used_days
               - b.pending_days AS available_days
    FROM employees AS e
    JOIN leave_balances AS b ON b.employee_id = e.employee_id
    WHERE e.department = ? AND b.leave_year = ?
      AND b.leave_type IN ('annual', 'pto')
    ORDER BY e.name
"""

PENDING_SQL = """
    SELECT r.request_id, r.leave_type, r.start_date, r.end_date,
           r.days AS working_days, r.submitted_on,
           a.name AS approver_name
    FROM leave_requests AS r
    LEFT JOIN employees AS a ON a.employee_id = r.approver_id
    WHERE r.employee_id = ? AND r.status = 'pending'
    ORDER BY r.start_date
"""


def long_date(day: date) -> str:
    """date(2026, 12, 31) -> '31 December 2026'."""
    return f"{day.day} {day:%B %Y}"


def fetch_department(department: str) -> list[dict]:
    """BALANCES_SQL's rows for `department`, this leave year, without
    their empty (NULL) columns (as hr_tools.fetch, which takes one
    parameter)."""
    with closing(connect()) as db:
        rows = db.execute(BALANCES_SQL, (department, TODAY.year)).fetchall()
    return [{column: value for column, value in dict(row).items()
             if value is not None} for row in rows]


def year_end_row(row: dict) -> dict:
    """One person's year-end numbers from their BALANCES_SQL row."""
    limit, use_by, rule = CARRY_OVER[row["leave_type"]]
    available = row["available_days"]
    person = {
        "employee": whose(row["employee_id"]),
        "office": row["office"],
        "payroll": row["payroll"],
        "leave_type": row["leave_type"],
        "available_days": available,
        "rule": f"{rule}: up to {limit} days carry over, to use by "
                f"{use_by.day} {use_by:%B}",
    }
    leaving = row.get("last_working_day")
    if leaving and date.fromisoformat(leaving) <= YEAR_END:
        person["leaving_on"] = long_date(date.fromisoformat(leaving))
        person["note"] = SETTLED_ON_LEAVING
        person["days_lost_on_31_december"] = 0
        person["days_carried_into_next_year"] = 0
    else:
        person["days_lost_on_31_december"] = max(0, available - limit)
        person["days_carried_into_next_year"] = min(available, limit)
        person["use_carried_days_by"] = long_date(use_by)
    pending = fetch(PENDING_SQL, row["employee_id"])
    if pending:
        person["pending_requests"] = pending
    return person


@tool(parse_docstring=True)
def year_end_leave(runtime: ToolRuntime[HRContext],
                   department: Department) -> dict:
    """Get one department's year-end leave review (People Operations
    only).

    Returns the department head, then one entry per person: their
    office and payroll (India or US), leave type (annual or pto), days
    available now, the carry-over rule with its handbook section, days
    lost on 31 December, days carried into next year and the date to
    use them by, and their pending leave requests (ID, type, dates,
    working days, approver). People leaving before 31 December are
    marked instead. Ends with the department's totals, added up by
    code. Use these numbers as they are; don't work any out.

    Args:
        runtime: Added by the agent, never by the model.
        department: The department to review.
    """
    viewer = fetch(VIEWER_SQL, runtime.context.employee_id)
    if not viewer or not may_read(hr_access(viewer[0]), "leave"):
        return NOT_HR
    if department not in DEPARTMENTS:
        return {"error": f"No department {department!r}; choose one of: "
                         + ", ".join(DEPARTMENTS)}
    return department_review(department)


def department_review(department: str) -> dict:
    """year_end_leave's result for `department`, without the permission
    check: for code that checks the memos against it (year_end.py)."""
    people = [year_end_row(row) for row in fetch_department(department)]
    head = fetch(HEAD_SQL, department)
    losing = [p for p in people if p["days_lost_on_31_december"] > 0]
    return {
        "department": department,
        "head": whose(head[0]["employee_id"]) if head else "unknown",
        "as_of": long_date(TODAY),
        "assumes": "no more leave is taken before 31 December and every "
                   "pending request is approved",
        "people": people,
        "totals": {
            "people": len(people),
            "people_losing_days": len(losing),
            "days_lost_on_31_december": sum(
                p["days_lost_on_31_december"] for p in losing),
            "pending_requests": sum(
                len(p.get("pending_requests", [])) for p in people),
        },
    }
