"""Leave tools that change data: submit a leave request (stage D).

In:  the leave type and dates the model fills in; who is asking
     (HRContext, from the sign-in).
Out: a question for the person ("Submit annual leave for 22–23
     December 2026 (2 working days)?"), then on Confirm the saved
     request (ID, working days, status pending, approver); or the
     existing one if it was already asked for, why it can't be saved,
     or that they cancelled.

Strategy: the model only proposes; code checks, then writes. Shape:
the inputs' types (real dates, a known leave type). Permission: no
`employee` input, so it can only book the signed-in person's leave.
Business rules from the Employee Handbook: a type their payroll has,
future dates in 2026, enough days left, at most 5 annual days during
probation in India (3.4.4), no overlap. Working days skip weekends
and the office's holidays (chapter 6). Every check passed → the
person confirms (interrupt(): the run pauses, the app shows Confirm
and Cancel); on Confirm the checks run again and the write follows in
one locked transaction: the request and the balance together.

Caveats:
- The only tool that writes; the read tools open the database
  read-only. Re-run build_hr_db.py to undo test writes.
- Same type and dates again returns the existing request (idempotent).
- Whole days only (no half days). The request stays pending until the
  manager approves it.
- The pause needs the agent's memory (memory=True, a thread_id) to
  continue; without it (the evals) the run stops at the question and
  nothing is saved.
"""

import logging
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import cache
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.types import interrupt

from ams_assistant.config import HR_DB_FILE, POLICIES_DIR, TODAY
from ams_assistant.hr_tools import HRContext, connect, whose

logger = logging.getLogger(__name__)

# The leave types each payroll has (Employee Handbook, chapters 4-5).
LEAVE_TYPES = {"India": ("annual", "sick", "casual"),
               "US": ("pto", "sick", "floating")}
# Employee Handbook 3.4.4: India payroll, annual leave during probation.
PROBATION_ANNUAL_LIMIT = 5
# The holiday calendar: Employee Handbook chapter 6, a section per office.
HANDBOOK_FILE = POLICIES_DIR / "people" / "employee_handbook.txt"
HOLIDAY_SECTIONS = {"Bengaluru": "6.3.1", "Pune": "6.4.1",
                    "Austin": "6.6.1"}
# The data holds one leave year.
LEAVE_YEAR = 2026
# Said for any unexpected failure: never a stack trace or SQL.
CANT_SAVE = ("Couldn't save the request right now; nothing was saved. "
             "Trying again later may work.")

# The approver is the manager.
EMPLOYEE_SQL = """
    SELECT e.office, e.status, e.manager_id, m.name AS approver_name
    FROM employees AS e
    LEFT JOIN employees AS m ON m.employee_id = e.manager_id
    WHERE e.employee_id = ?
"""

BALANCE_SQL = """
    SELECT used_days, pending_days,
           entitled_days + carried_over_days - used_days - pending_days
               AS available_days
    FROM leave_balances
    WHERE employee_id = ? AND leave_type = ?
"""

# Requests that still count: not rejected or cancelled.
ACTIVE_SQL = """
    SELECT request_id, leave_type, start_date, end_date, days AS
           working_days, status
    FROM leave_requests
    WHERE employee_id = ? AND status IN ('pending', 'approved')
"""


@cache
def holidays(office: str) -> frozenset[date]:
    """The office's fixed holidays, read from the handbook's table:
    'Christmas | 25 December 2026 | Friday'."""
    lines = HANDBOOK_FILE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith(f"{HOLIDAY_SECTIONS[office]} "))
    days = set()
    for line in lines[start + 1:]:
        if re.match(r"\d+\.\d+(?:\.\d+)* ", line):
            break  # the next section
        match = re.search(r"\| (\d{1,2} \w+ \d{4}) \|", line)
        if match:
            days.add(datetime.strptime(match.group(1), "%d %B %Y").date())
    return frozenset(days)


def working_days(start: date, end: date, office: str) -> int:
    """Weekdays from start to end (both included) that aren't the
    office's holidays."""
    days, current = 0, start
    while current <= end:
        if current.weekday() < 5 and current not in holidays(office):
            days += 1
        current += timedelta(days=1)
    return days


def refuse(reason: str) -> dict:
    """A rule said no: the reason goes back to the model to pass on."""
    return {"error": f"Not saved: {reason}"}


def shape_problem(payroll: str, leave_type: str, start: date,
                  end: date) -> str | None:
    """What the input types can't check: a type their payroll has,
    and dates that can be booked. None if fine."""
    if leave_type not in LEAVE_TYPES[payroll]:
        return (f"{payroll} payroll leave types are "
                f"{', '.join(LEAVE_TYPES[payroll])}.")
    if end < start:
        return "the end date is before the start date."
    if start <= TODAY:
        return (f"leave can only be requested for dates after today "
                f"({TODAY:%-d %B %Y}).")
    if end.year != LEAVE_YEAR:
        return f"only leave year {LEAVE_YEAR} can be booked."
    return None


def same_and_overlap(active: list[dict], leave_type: str, start: date,
                     end: date) -> tuple[dict | None, dict | None]:
    """Among the person's pending and approved requests: the same
    request (type and dates), and one whose dates overlap."""
    first, last = start.isoformat(), end.isoformat()
    same = next((r for r in active
                 if (r["leave_type"], r["start_date"], r["end_date"])
                 == (leave_type, first, last)), None)
    overlap = next((r for r in active
                    if r["start_date"] <= last and r["end_date"] >= first),
                   None)
    return same, overlap


def rule_problem(person: sqlite3.Row, payroll: str, balance, leave_type:
                 str, days: int) -> str | None:
    """The Employee Handbook's rules on the balance. None if fine."""
    available = balance["available_days"] if balance else 0
    if available < days:
        return (f"{days} working days asked, {available:g} {leave_type} "
                f"days available.")
    if (payroll == "India" and person["status"] == "probation"
            and leave_type == "annual"):
        taken = balance["used_days"] + balance["pending_days"]
        if taken + days > PROBATION_ANNUAL_LIMIT:
            return (f"during probation, India payroll employees may use "
                    f"up to {PROBATION_ANNUAL_LIMIT} annual days "
                    f"(Employee Handbook 3.4.4); {taken:g} already used "
                    f"or pending.")
    return None


def check_request(db: sqlite3.Connection, employee_id: str,
                  leave_type: str, start: date,
                  end: date) -> tuple[dict | None, dict]:
    """Every check, nothing written: (the answer, if a check decides
    it: a refusal or the request already saved; else None, and what
    saving needs: the person, working days, days available)."""
    person = db.execute(EMPLOYEE_SQL, (employee_id,)).fetchone()
    payroll = "US" if person["office"] == "Austin" else "India"

    problem = shape_problem(payroll, leave_type, start, end)
    if problem:
        return refuse(problem), {}
    days = working_days(start, end, person["office"])
    if days == 0:
        return refuse("there are no working days in those dates "
                      "(weekends and office holidays)."), {}

    # Idempotent: the same request again returns the one already saved.
    active = [dict(row) for row in db.execute(ACTIVE_SQL, (employee_id,))]
    same, overlap = same_and_overlap(active, leave_type, start, end)
    if same:
        return {"employee": whose(employee_id), "saved": False,
                "note": "Already requested; nothing new was saved.",
                "request": same}, {}
    if overlap:
        return refuse(f"it overlaps {overlap['request_id']} "
                      f"({overlap['start_date']} to "
                      f"{overlap['end_date']}, {overlap['status']})."), {}

    balance = db.execute(BALANCE_SQL, (employee_id, leave_type)).fetchone()
    problem = rule_problem(person, payroll, balance, leave_type, days)
    if problem:
        return refuse(problem), {}
    return None, {"person": person, "days": days,
                  "available": balance["available_days"]}


def leave_name(leave_type: str) -> str:
    """A leave type as people write it: 'annual leave', 'PTO'."""
    return "PTO" if leave_type == "pto" else f"{leave_type} leave"


def date_range(start: date, end: date) -> str:
    """'22–23 December 2026', '30 December 2026', or across months
    '30 November – 2 December 2026'."""
    if start == end:
        return f"{end:%-d %B %Y}"
    if start.month == end.month:
        return f"{start:%-d}–{end:%-d %B %Y}"
    return f"{start:%-d %B} – {end:%-d %B %Y}"


def confirm_question(leave_type: str, start: date, end: date,
                     plan: dict) -> str:
    """What the person is asked before anything is saved."""
    days, left = plan["days"], plan["available"] - plan["days"]
    return (f"Submit {leave_name(leave_type)} for {date_range(start, end)} "
            f"({days} working day{'s' if days != 1 else ''})? You'll have "
            f"{left:g} {leave_name(leave_type).removesuffix(' leave')} "
            f"days left, and "
            f"{plan['person']['approver_name']} will be asked to approve "
            f"it.")


def save_request(db: sqlite3.Connection, employee_id: str,
                 leave_type: str, start: date, end: date) -> dict:
    """Check every rule again, then save; runs inside the caller's
    locked transaction, so nothing changes between the checks and the
    write."""
    answer, plan = check_request(db, employee_id, leave_type, start, end)
    if answer:
        return answer
    person, days = plan["person"], plan["days"]

    # Every check passed: the request and its pending days, together.
    last = db.execute("SELECT MAX(request_id) FROM leave_requests")
    number = int(last.fetchone()[0].removeprefix("LR-")) + 1
    request_id = f"LR-{number:04d}"
    db.execute(
        "INSERT INTO leave_requests VALUES (?, ?, ?, ?, ?, ?, 'pending', "
        "?, ?)",
        (request_id, employee_id, leave_type, start.isoformat(),
         end.isoformat(), days, TODAY.isoformat(), person["manager_id"]))
    db.execute(
        "UPDATE leave_balances SET pending_days = pending_days + ? "
        "WHERE employee_id = ? AND leave_type = ?",
        (days, employee_id, leave_type))
    return {"employee": whose(employee_id), "saved": True,
            "request": {"request_id": request_id, "leave_type": leave_type,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(), "working_days": days,
                        "status": "pending",
                        "approver_name": person["approver_name"]},
            "available_after": plan["available"] - days}


def save_locked(employee_id: str, leave_type: str, start: date,
                end: date) -> dict:
    """save_request in one locked transaction; any failure → CANT_SAVE,
    with the details in the log."""
    try:
        # isolation_level=None: we open the transaction ourselves.
        with closing(sqlite3.connect(HR_DB_FILE,
                                     isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            # IMMEDIATE: lock now, so no other write lands between our
            # checks and our write (two requests can't take the same
            # days or the same ID).
            db.execute("BEGIN IMMEDIATE")
            try:
                result = save_request(db, employee_id, leave_type, start,
                                      end)
            except Exception:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
            return result
    except Exception:
        # The details go to the log, never to the model or the user.
        logger.exception("submit_leave_request failed")
        return {"error": CANT_SAVE}


@tool(parse_docstring=True)
def submit_leave_request(
    runtime: ToolRuntime[HRContext],
    leave_type: Literal["annual", "sick", "casual", "pto", "floating"],
    start_date: date,
    end_date: date,
) -> dict:
    """Submit a leave request for the employee you are helping.

    Checks it, asks them to confirm (the app shows the request with
    Confirm and Cancel), then saves it as pending for their manager to
    approve. Returns the request ID, working days (weekends and office
    holidays not counted), approver and the days left after it; or why
    it can't be saved; or that they cancelled. Use it only when they
    ask to book or apply for leave, with the dates they gave. Call it
    straight away: don't ask them to confirm first yourself.

    Args:
        runtime: Added by the agent, never by the model.
        leave_type: The type they asked for. India offices: annual
            (vacation), sick or casual; the US office: pto (vacation),
            sick or floating. If they didn't say, ask them; don't guess.
        start_date: The first day of leave, e.g. 2026-12-22.
        end_date: The last day of leave; the same as start_date for one
            day.
    """
    employee_id = runtime.context.employee_id
    try:
        with closing(connect()) as db:  # read-only: just the checks
            answer, plan = check_request(db, employee_id, leave_type,
                                         start_date, end_date)
    except Exception:
        logger.exception("submit_leave_request failed")
        return {"error": CANT_SAVE}
    if answer:  # refused, or already saved: no question
        return answer
    # Every check passed: ask them (stage H). interrupt() pauses the run
    # here and the chat is saved; on their reply the tool runs again
    # from the top (the checks too) and interrupt() returns the reply.
    # Outside any try: the pause is an exception LangGraph must get.
    reply = interrupt({"question": confirm_question(
        leave_type, start_date, end_date, plan)})
    if reply != "confirm":
        return {"employee": whose(employee_id), "saved": False,
                "note": "They cancelled; nothing was saved."}
    return save_locked(employee_id, leave_type, start_date, end_date)
