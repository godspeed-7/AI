"""Booking leave: checks, a person's yes, then one save (walks 9, 10).

In:  submit_leave_request(leave_type, start_date, end_date), called by
     the model for the signed-in employee only (no `employee` input).
Out: JSON for the model: the saved request (pending, with its approver),
     the request already on record, "cancelled", or why it can't be
     booked. On the way, a pause: interrupt() hands the app the exact
     action to show with Confirm / Cancel.

Strategy, in order (walk 8's shape and rule checks live here, with the
only write):
1. Shape: a leave type the person has this year, real dates, today or
   later, start before end, within this leave year.
2. Rules (Employee handbook): days = working days, without weekends
   and the office's holidays (4.2); enough days available; no overlap
   with a pending or approved request; on India probation, at least 5
   annual days in all (3.4.4). Less notice than 4.3.4 asks (10 days,
   15 for 5+ days) is a warning shown with the action, not a block:
   the handbook calls those planning targets.
3. The same request already pending or approved: return it (walk 10).
4. interrupt(): the person sees the real action and confirms or
   cancels. Nothing is written before this point: on resume, the code
   above runs again (only reads), then the answer comes back.
5. Save once (walk 10): one transaction, locked (BEGIN IMMEDIATE),
   that re-checks steps 2-3, adds the request and moves the days to
   "pending" in the balance. The database's unique index refuses a
   second copy even if two clicks race.

Caveats: needs a checkpointer (the pause is saved there; agent.py). The
manager's approve / reject is not here yet. Half days aren't bookable.
"""

import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta

from langchain.tools import ToolRuntime, tool
from langgraph.types import interrupt

from ams_agent.config import PAYROLL, TODAY
from ams_agent.context import Context
from ams_agent.db import connect

PROBATION_ANNUAL_DAYS = 5  # Employee 3.4.4 (India payroll)
NOTICE_DAYS, LONG_NOTICE_DAYS, LONG_LEAVE = 10, 15, 5  # Employee 4.3.4


def _working_days(con, office: str, start: date, end: date) -> list[date]:
    """The days in start..end that count: no weekends, no holidays."""
    off = {r[0] for r in con.execute(
        "SELECT holiday_date FROM holidays WHERE office = ?", (office,))}
    days, d = [], start
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in off:
            days.append(d)
        d += timedelta(days=1)
    return days


def _existing(con, who: str, leave_type: str, start: date, end: date):
    """The same request, already pending or approved, or None."""
    row = con.execute(
        "SELECT request_id, status, days FROM leave_requests"
        " WHERE employee_id = ? AND leave_type = ? AND start_date = ?"
        " AND end_date = ? AND status IN ('pending', 'approved')",
        (who, leave_type, start.isoformat(), end.isoformat())).fetchone()
    return dict(row) if row else None


def _problems(con, context: Context, leave_type: str, start: date,
              end: date, days: int) -> list[str]:
    """What the rules forbid (step 2); empty when it can be booked."""
    who = context.employee_id
    balance = con.execute(
        "SELECT entitled_days + carried_over_days - used_days - pending_days"
        " AS available, used_days + pending_days AS taken"
        " FROM leave_balances WHERE employee_id = ? AND leave_year = ?"
        " AND leave_type = ?", (who, TODAY.year, leave_type)).fetchone()
    problems = []
    if days > balance["available"]:
        problems.append(f"only {balance['available']:g} {leave_type} days"
                        f" are available, and this needs {days}")
    overlap = con.execute(
        "SELECT request_id, leave_type, start_date, end_date"
        " FROM leave_requests WHERE employee_id = ?"
        " AND status IN ('pending', 'approved')"
        " AND start_date <= ? AND end_date >= ?",
        (who, end.isoformat(), start.isoformat())).fetchone()
    if overlap:
        problems.append(f"it overlaps {overlap['request_id']}"
                        f" ({overlap['leave_type']}, {overlap['start_date']}"
                        f" to {overlap['end_date']})")
    status = con.execute("SELECT status FROM employees WHERE employee_id = ?",
                         (who,)).fetchone()["status"]
    if (status == "probation" and leave_type == "annual"
            and PAYROLL.get(context.office) == "India"
            and balance["taken"] + days > PROBATION_ANNUAL_DAYS):
        problems.append(
            f"during probation at most {PROBATION_ANNUAL_DAYS} annual days"
            f" can be used in all; {balance['taken']:g} are already used or"
            " pending (Employee 3.4.4)")
    return problems


def _save(context: Context, leave_type: str, start: date, end: date,
          days: int, approver: str) -> dict:
    """One transaction: re-check, add the request, move the days."""
    who = context.employee_id
    with closing(connect(write=True)) as con:
        con.execute("BEGIN IMMEDIATE")  # locks out a second writer
        try:
            if found := _existing(con, who, leave_type, start, end):
                con.rollback()
                return {"already_on_record": found}
            if problems := _problems(con, context, leave_type, start, end,
                                     days):
                con.rollback()
                return {"error": "can't book: " + "; ".join(problems)}
            last = con.execute(
                "SELECT MAX(CAST(SUBSTR(request_id, 4) AS INTEGER))"
                " FROM leave_requests").fetchone()[0] or 0
            request_id = f"LR-{last + 1:04d}"
            con.execute(
                "INSERT INTO leave_requests VALUES (?, ?, ?, ?, ?, ?,"
                " 'pending', ?, ?)",
                (request_id, who, leave_type, start.isoformat(),
                 end.isoformat(), float(days), TODAY.isoformat(), approver))
            con.execute(
                "UPDATE leave_balances SET pending_days = pending_days + ?"
                " WHERE employee_id = ? AND leave_year = ? AND leave_type = ?",
                (days, who, TODAY.year, leave_type))
            con.commit()
        except sqlite3.IntegrityError:  # the unique index: a racing twin
            con.rollback()
            with closing(connect()) as ro:
                return {"already_on_record":
                        _existing(ro, who, leave_type, start, end)}
    return {"booked": {"request_id": request_id, "leave_type": leave_type,
                       "start_date": start.isoformat(),
                       "end_date": end.isoformat(), "days": days,
                       "status": "pending", "approver_id": approver}}


@tool(parse_docstring=True)
def submit_leave_request(runtime: ToolRuntime[Context], leave_type: str,
                         start_date: date, end_date: date) -> str:
    """Book leave for the signed-in employee (only for themselves).

    Code checks the dates and the rules, then the employee sees the
    exact request and confirms or cancels it; nothing is booked without
    their yes. A booked request is pending until their manager decides.

    Args:
        leave_type: One of the employee's leave types: annual, sick or
            casual (India); pto, sick or floating (US).
        start_date: The first day of leave, e.g. 2026-12-22.
        end_date: The last day of leave (the same day for one day).
    """
    context = runtime.context
    who = context.employee_id
    with closing(connect()) as con:
        types = {r[0] for r in con.execute(
            "SELECT leave_type FROM leave_balances WHERE employee_id = ?"
            " AND leave_year = ?", (who, TODAY.year))}
        if leave_type not in types:
            return json.dumps({"error": f"no {leave_type!r} leave: choose"
                               f" one of {', '.join(sorted(types))}"})
        if start_date < TODAY or end_date < start_date:
            return json.dumps({"error": "the dates must be today or later,"
                               " and the start no later than the end"})
        if end_date.year != TODAY.year:
            return json.dumps({"error": f"only {TODAY.year} leave can be"
                               " booked now; book next year's separately"})
        days = len(_working_days(con, context.office, start_date, end_date))
        if not days:
            return json.dumps({"error": "those dates are all weekends or"
                               " office holidays: no leave is needed"})
        if found := _existing(con, who, leave_type, start_date, end_date):
            return json.dumps({"already_on_record": found})
        if problems := _problems(con, context, leave_type, start_date,
                                 end_date, days):
            return json.dumps({"error": "can't book: " + "; ".join(problems)})
        approver = con.execute(
            "SELECT manager_id FROM employees WHERE employee_id = ?",
            (who,)).fetchone()["manager_id"]
    notice = (start_date - TODAY).days
    wanted = LONG_NOTICE_DAYS if days >= LONG_LEAVE else NOTICE_DAYS
    warning = (f"Only {notice} days' notice; the handbook asks for {wanted}"
               " (Employee 4.3.4), so your manager may ask to move it."
               if notice < wanted else "")
    answer = interrupt({
        "action": "submit_leave_request",
        "summary": (f"Book {leave_type} leave: {start_date:%a %d %b %Y}"
                    f" to {end_date:%a %d %b %Y} ({days} working day"
                    f"{'s' if days > 1 else ''}), for approval by"
                    f" {approver}."),
        "warning": warning,
    })
    if not (isinstance(answer, dict) and answer.get("confirmed")):
        return json.dumps({"cancelled": "the employee cancelled it;"
                           " nothing was booked"})
    return json.dumps(_save(context, leave_type, start_date, end_date, days,
                            approver))
