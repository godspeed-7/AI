"""Approval tools: a manager approves or rejects leave (stage H).

In:  who is asking (HRContext, from the sign-in); for a decision, the
     list the model fills in: [LR-0189 → approve, LR-0192 → reject].
Out: the requests waiting for their approval; or one question for
     the whole list ("Approve: Rahul Verma, annual leave, 3–4 December
     2026 …? Confirm / Cancel"), then what was decided and skipped.

Strategy: two tools, a read and a write (the write needs checks and
a "Confirm?"), only in managers' agents (agent.tools_for).
get_requests_to_approve lists only the pending requests whose
approver is the asker. decide_leave_requests takes every decision in
one call: code checks each request (permissions.may_decide: its
approver, not your own; still pending), asks once for the whole list
(interrupt(), as submit_leave_request does), then saves them all in
one locked transaction, checking again first: the status, and the
balance's days (approve: pending → used; reject: pending released),
so used = approved days and pending = pending days.

Caveats:
- An ID that isn't theirs to decide and one that doesn't exist get the
  same "not allowed", so the agent can't find out others' requests.
- No rejection reason or decision date: the data has no columns for
  them. No email to the employee: they see the status when they ask.
"""

import logging
import sqlite3
from contextlib import closing
from datetime import date
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from ams_assistant.config import HR_DB_FILE
from ams_assistant.hr_tools import HRContext, connect, fetch, whose
from ams_assistant.leave_tools import date_range, leave_name
from ams_assistant.permissions import may_decide

logger = logging.getLogger(__name__)

# Said for any unexpected failure: never a stack trace or SQL.
CANT_SAVE = ("Couldn't save the decisions right now; nothing was "
             "changed. Trying again later may work.")
NOT_ALLOWED = ("not allowed: you can decide only requests waiting for "
               "your approval")

# Pending requests waiting for this approver, never their own.
TO_APPROVE_SQL = """
    SELECT r.request_id, e.name AS employee_name, r.employee_id,
           r.leave_type, r.start_date, r.end_date, r.days AS working_days,
           r.submitted_on
    FROM leave_requests AS r
    JOIN employees AS e ON e.employee_id = r.employee_id
    WHERE r.approver_id = ? AND r.status = 'pending'
      AND r.employee_id != r.approver_id
    ORDER BY r.start_date
"""

REQUEST_SQL = """
    SELECT r.request_id, r.employee_id, e.name AS employee_name,
           r.leave_type, r.start_date, r.end_date, r.days, r.status,
           r.approver_id
    FROM leave_requests AS r
    JOIN employees AS e ON e.employee_id = r.employee_id
    WHERE r.request_id = ?
"""

# The status each decision sets.
STATUS = {"approve": "approved", "reject": "rejected"}


class LeaveDecision(BaseModel):
    """One request and what to do with it."""

    request_id: str = Field(description="The request's ID, e.g. LR-0189, "
                            "from get_requests_to_approve.")
    decision: Literal["approve", "reject"]


@tool
def get_requests_to_approve(runtime: ToolRuntime[HRContext]) -> dict:
    """List the leave requests waiting for the approval of the person
    you are helping: requests from the people who report to them, never
    their own leave (their manager decides it; get_leave_requests shows
    it). Gives who, type, dates, working days and the request ID. Use
    it when they ask what's waiting for them, or to find the IDs of
    requests they want to approve or reject."""
    approver_id = runtime.context.employee_id
    return {"approver": whose(approver_id),
            "requests": fetch(TO_APPROVE_SQL, approver_id)}


def sort_decisions(db: sqlite3.Connection, approver_id: str,
                   decisions: list[LeaveDecision],
                   ) -> tuple[list[dict], list[dict]]:
    """Check each decision: (the ones that can go ahead, each its
    request row + "decision"; the skipped ones, each with why)."""
    ready, skipped, seen = [], [], set()
    for item in decisions:
        request_id = item.request_id.strip().upper()
        if request_id in seen:
            skipped.append({"request_id": request_id,
                            "reason": "listed twice; the first counts"})
            continue
        seen.add(request_id)
        row = db.execute(REQUEST_SQL, (request_id,)).fetchone()
        if row is None or not may_decide(approver_id, dict(row)):
            skipped.append({"request_id": request_id,
                            "reason": NOT_ALLOWED})
        elif row["status"] != "pending":
            skipped.append({"request_id": request_id,
                            "reason": f"already {row['status']}"})
        else:
            ready.append({**dict(row), "decision": item.decision})
    return ready, skipped


def line(row: dict) -> str:
    """One decision, as the question writes it: '- **Approve**: Rahul
    Verma, annual leave, 3–4 December 2026 (2 working days)'."""
    days = row["days"]
    when = date_range(date.fromisoformat(row["start_date"]),
                      date.fromisoformat(row["end_date"]))
    return (f"- **{row['decision'].title()}**: {row['employee_name']}, "
            f"{leave_name(row['leave_type'])}, {when} ({days:g} working "
            f"day{'s' if days != 1 else ''})")


def question(ready: list[dict]) -> str:
    """What the approver is asked: every decision, one line each."""
    count = len(ready)
    return (f"You're about to decide {count} leave "
            f"request{'s' if count != 1 else ''}:\n\n"
            + "\n".join(line(row) for row in ready))


def save_decisions(db: sqlite3.Connection, approver_id: str,
                   decisions: list[LeaveDecision]) -> dict:
    """Check every decision again, then save the ones that can go
    ahead; inside the caller's locked transaction."""
    ready, skipped = sort_decisions(db, approver_id, decisions)
    for r in ready:
        db.execute("UPDATE leave_requests SET status = ? "
                   "WHERE request_id = ? AND status = 'pending'",
                   (STATUS[r["decision"]], r["request_id"]))
        # Keep used = approved days, pending = pending days.
        used = r["days"] if r["decision"] == "approve" else 0
        db.execute("UPDATE leave_balances SET pending_days = pending_days"
                   " - ?, used_days = used_days + ? "
                   "WHERE employee_id = ? AND leave_type = ?",
                   (r["days"], used, r["employee_id"], r["leave_type"]))
    return {"approver": whose(approver_id), "saved": bool(ready),
            "decided": [{"request_id": r["request_id"],
                         "employee": r["employee_name"],
                         "status": STATUS[r["decision"]]} for r in ready],
            "skipped": skipped}


def save_locked(approver_id: str, decisions: list[LeaveDecision]) -> dict:
    """save_decisions in one locked transaction: all or nothing; any
    failure → CANT_SAVE, with the details in the log."""
    try:
        with closing(sqlite3.connect(HR_DB_FILE,
                                     isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            try:
                result = save_decisions(db, approver_id, decisions)
            except Exception:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
            return result
    except Exception:
        logger.exception("decide_leave_requests failed")
        return {"error": CANT_SAVE}


@tool(parse_docstring=True)
def decide_leave_requests(runtime: ToolRuntime[HRContext],
                          decisions: list[LeaveDecision]) -> dict:
    """Approve or reject leave requests waiting for the approval of the
    person you are helping: from the people who report to them, never
    their own leave (their manager decides it).

    Put every decision they asked for in this one call. It checks each
    request, asks them to confirm the whole list (the app shows it with
    Confirm and Cancel), then saves them all together. Returns what was
    decided, and any request skipped (not theirs to decide, or already
    decided). Call it straight away: don't ask them to confirm first
    yourself.

    Args:
        runtime: Added by the agent, never by the model.
        decisions: One entry per request: its ID and approve or reject.
    """
    approver_id = runtime.context.employee_id
    try:
        with closing(connect()) as db:  # read-only: just the checks
            ready, skipped = sort_decisions(db, approver_id, decisions)
    except Exception:
        logger.exception("decide_leave_requests failed")
        return {"error": CANT_SAVE}
    if not ready:  # nothing they may decide: no question
        return {"saved": False, "skipped": skipped}
    # Ask once for the whole list (stage H). Outside any try: the pause
    # is an exception LangGraph must get. On their reply the tool runs
    # again from the top, the checks too.
    reply = interrupt({"question": question(ready)})
    if reply != "confirm":
        return {"saved": False, "skipped": skipped,
                "note": "They cancelled; nothing was changed."}
    return save_locked(approver_id, decisions)
