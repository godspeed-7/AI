"""The agent's tools: code that looks up facts for the model (walks 7, 8).

In:  the signed-in employee's context (context.py) and, optionally, who
     the question is about (`employee`: a name or ID, from the model).
Out: TOOLS, the list given to the agent: 10 record tools and get_team
     (JSON text, saying whose records), search_policies
     (policy_search.py, handbook sections) and submit_leave_request
     (leave_booking.py, the only tool that writes).

Strategy: fixed SQL tools: we write every query, the model only picks
the tool and whom it is about (never text-to-SQL). Before any query,
permissions.target() decides whose records may be read: the asker's
own, their team's (managers), anyone's (hr); otherwise nothing is read
and the tool says "Not allowed" (walk 8). get_team exists for managers
only: it is offered by role (permissions.offer_by_role) and checks the
role again itself. Deterministic: code does the sums and the date
checks (available days, time at AMS, overdue), the model explains.
People appear as IDs, never names (Gemini doesn't need them). Errors
and "nothing found" come back as JSON, so the model can say so.

Caveats: employee_private (bank, PAN, Aadhaar, SSN) has no tool, on
purpose. Same permission rule for every record type.
"""

import json
from contextlib import closing
from datetime import date

from langchain.tools import ToolRuntime, tool

from ams_agent.config import PAYROLL, TODAY
from ams_agent.context import Context, Role
from ams_agent.db import connect, direct_reports
from ams_agent.leave_booking import submit_leave_request
from ams_agent.memory import forget_preferences, remember_preference
from ams_agent.permissions import NOT_ALLOWED, target
from ams_agent.policy_search import search_policies


def _days(value: float) -> int | float:
    """7.0 -> 7, 0.5 -> 0.5: whole days read as whole numbers."""
    return int(value) if float(value).is_integer() else value


def _rows(sql: str, *params) -> list[dict]:
    """A fixed query's rows, as dicts (None dropped); values go in as ?
    parameters, never into the SQL text."""
    with closing(connect()) as con:
        rows = con.execute(sql, params).fetchall()
    return [{k: v for k, v in dict(r).items() if v is not None} for r in rows]


def _reply(rows: list[dict], what: str, whose: str) -> str:
    """JSON for the model, saying whose records these are; an explicit
    note when there is nothing."""
    if not rows:
        return json.dumps({"employee_id": whose, "found": 0,
                           "note": f"no {what} on record"})
    return json.dumps({"employee_id": whose, "records": rows})


def _time_since(start: str) -> str:
    """'2021-08-09' -> '5 years 3 months' (to TODAY)."""
    d = date.fromisoformat(start)
    months = (TODAY.year - d.year) * 12 + TODAY.month - d.month
    months -= TODAY.day < d.day
    return f"{months // 12} years {months % 12} months"


@tool(parse_docstring=True)
def get_profile(runtime: ToolRuntime[Context],
                employee: str | None = None) -> str:
    """Get an employee's employment record.

    Returns job title, department, grade (L1 to L6), office and payroll
    (India or US), manager's employee ID, join date and time at AMS,
    and status: probation (with its end date), confirmed, or
    notice_period (with the resignation date and last working day).

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    rows = _rows(
        "SELECT job_title, department, grade, office, manager_id,"
        " join_date, status, probation_end_date, resignation_date,"
        " last_working_day FROM employees WHERE employee_id = ?",
        whose)
    if not rows:
        return _reply(rows, "employment record", whose)
    profile = {"employee_id": whose, **rows[0]}
    profile["payroll"] = PAYROLL.get(profile["office"], "unknown")
    profile["time_at_ams"] = _time_since(profile["join_date"])
    return json.dumps(profile)


@tool(parse_docstring=True)
def get_leave_balance(runtime: ToolRuntime[Context],
                      employee: str | None = None) -> str:
    """Get an employee's leave balance for this year.

    For each leave type (annual, sick and casual in India; pto, sick and
    floating in the US): days entitled, carried over from last year,
    used, pending approval, and available to book now.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    rows = _rows(
        "SELECT leave_type, entitled_days, carried_over_days, used_days,"
        " pending_days FROM leave_balances WHERE employee_id = ?"
        " AND leave_year = ?",
        whose, TODAY.year)
    return _reply([
        {
            "leave_type": r["leave_type"],
            "year": TODAY.year,
            "entitled": _days(r["entitled_days"]),
            "carried_over": _days(r["carried_over_days"]),
            "used": _days(r["used_days"]),
            "pending": _days(r["pending_days"]),
            "available": _days(
                r["entitled_days"] + r["carried_over_days"]
                - r["used_days"] - r["pending_days"]),
        }
        for r in rows
    ], f"leave balance for {TODAY.year}", whose)


@tool(parse_docstring=True)
def get_leave_requests(runtime: ToolRuntime[Context],
                       employee: str | None = None) -> str:
    """Get an employee's leave requests, newest first.

    Each with leave type, start and end dates, days, status (pending,
    approved, rejected or cancelled), when it was submitted and the
    approver's employee ID.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    rows = _rows(
        "SELECT request_id, leave_type, start_date, end_date, days, status,"
        " submitted_on, approver_id FROM leave_requests"
        " WHERE employee_id = ? ORDER BY start_date DESC",
        whose)
    for r in rows:
        r["days"] = _days(r["days"])
    return _reply(rows, "leave requests", whose)


@tool(parse_docstring=True)
def get_projects(runtime: ToolRuntime[Context],
                 employee: str | None = None) -> str:
    """Get an employee's project assignments, current first.

    Each with the project's ID, name, client and industry, whether it
    runs in an ODC (a secure client room), the project manager's
    employee ID, the share of time on it, the assignment's dates and
    whether it is current. Past assignments show when they ended.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    rows = _rows(
        "SELECT p.project_id, p.name, p.client, p.industry, p.odc,"
        " p.project_manager_id, a.allocation_percent,"
        " a.start_date, a.end_date, p.end_date AS project_end_date"
        " FROM project_assignments a JOIN projects p USING (project_id)"
        " WHERE a.employee_id = ? ORDER BY a.start_date DESC",
        whose)
    for r in rows:
        r["current"] = r.get("end_date", "9999") >= TODAY.isoformat()
    rows.sort(key=lambda r: not r["current"])
    return _reply(rows, "project assignments", whose)


@tool(parse_docstring=True)
def get_pay(runtime: ToolRuntime[Context],
            employee: str | None = None) -> str:
    """Get an employee's pay history, newest first.

    Each change of annual fixed pay with its date (effective_from), the
    reason (joining, annual_review, promotion...) and the currency.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    return _reply(_rows(
        "SELECT effective_from, reason, annual_pay, currency FROM salaries"
        " WHERE employee_id = ? ORDER BY effective_from DESC",
        whose), "pay history", whose)


@tool(parse_docstring=True)
def get_ratings(runtime: ToolRuntime[Context],
                employee: str | None = None) -> str:
    """Get an employee's yearly performance ratings.

    One per review year, newest first, e.g. "Meets expectations".

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    return _reply(_rows(
        "SELECT review_year, rating FROM ratings WHERE employee_id = ?"
        " ORDER BY review_year DESC",
        whose), "ratings", whose)


@tool(parse_docstring=True)
def get_expense_claims(runtime: ToolRuntime[Context],
                       employee: str | None = None) -> str:
    """Get an employee's expense claims, newest first.

    Each with trip, category (hotel, daily_allowance, flight...), city,
    nights, amount and currency, the expense and submission dates,
    whether a receipt or a lost-receipt declaration is attached, status
    (submitted, approved, paid, rejected) and the approver's ID.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    return _reply(_rows(
        "SELECT claim_id, trip_id, category, description, city, nights,"
        " amount, currency, expense_date, submitted_on, receipt_attached,"
        " lost_receipt_declaration, status, approver_id FROM expense_claims"
        " WHERE employee_id = ? ORDER BY expense_date DESC",
        whose), "expense claims", whose)


@tool(parse_docstring=True)
def get_assets(runtime: ToolRuntime[Context],
               employee: str | None = None) -> str:
    """Get the equipment AMS has issued to an employee.

    Laptops, phones, monitors and accessories, each with model, build,
    issue date, status (assigned, retired, lost, returned...) and when
    it ended. A laptop's issue date is what its refresh is counted from.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    return _reply(_rows(
        "SELECT asset_id, asset_type, build, model, issued_on, status,"
        " ended_on, purpose FROM assets WHERE employee_id = ?"
        " ORDER BY status = 'assigned' DESC, issued_on DESC",
        whose), "equipment", whose)


@tool(parse_docstring=True)
def get_tickets(runtime: ToolRuntime[Context],
                employee: str | None = None) -> str:
    """Get an employee's IT service desk tickets, newest first.

    Each with category, request type (lost, access, repair...), summary,
    the equipment it is about, incident, opened and resolved dates,
    status, who approved it, and whether a police report was filed.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    return _reply(_rows(
        "SELECT ticket_id, asset_id, category, request_type, summary,"
        " incident_date, opened_on, resolved_on, status, approved_by,"
        " police_report FROM servicedesk_tickets WHERE employee_id = ?"
        " ORDER BY opened_on DESC",
        whose), "service desk tickets", whose)


@tool(parse_docstring=True)
def get_trainings(runtime: ToolRuntime[Context],
                  employee: str | None = None) -> str:
    """Get an employee's assigned trainings, open ones first.

    Each with course, reason (annual, role, ...), assigned and due dates,
    completed date if done, and whether it is open or overdue today.

    Args:
        employee: Leave empty for the signed-in employee's own records.
            For someone else: their name or employee ID, e.g. "Ananya
            Iyer" or "AMS-1015" (code checks whether this is allowed).
    """
    whose, refused = target(runtime.context, employee)
    if refused:
        return json.dumps({"error": refused})
    rows = _rows(
        "SELECT course, reason, assigned_on, due_date, completed_on"
        " FROM trainings WHERE employee_id = ? ORDER BY due_date DESC",
        whose)
    for r in rows:
        r["open"] = "completed_on" not in r
        r["overdue"] = r["open"] and r["due_date"] < TODAY.isoformat()
    rows.sort(key=lambda r: not r["open"])
    return _reply(rows, "trainings", whose)


@tool
def get_team(runtime: ToolRuntime[Context]) -> str:
    """Get the signed-in manager's team: the people who report to them.

    Each with employee ID, job title, grade, office and status. Use the
    IDs with the other tools to look at a team member's records.
    """
    if Role.MANAGER not in runtime.context.roles:  # offered to managers
        return json.dumps({"error": NOT_ALLOWED})  # only; checked again
    return _reply(direct_reports(runtime.context.employee_id),
                  "direct reports", runtime.context.employee_id)


TOOLS = [get_profile, get_leave_balance, get_leave_requests, get_projects,
         get_pay, get_ratings, get_expense_claims, get_assets, get_tickets,
         get_trainings, get_team, search_policies, submit_leave_request,
         remember_preference, forget_preferences]
