"""The agent's tools: code that looks up facts for the model.

In:  the signed-in employee's ID, from the runtime context (context.py).
Out: TOOLS, the list given to the agent; each tool returns JSON text.

Strategy: deterministic tools. Code does the lookups and the sums
(available = entitled + carried over - used - pending), so the model
only explains the result and never does the arithmetic. No tool takes
an employee ID from the model: it reads runtime.context, which the
model can't change.

Caveats: one tool so far (walk 1); the rest arrive one step at a time.
"""

import json
from contextlib import closing

from langchain.tools import ToolRuntime, tool

from ams_agent.config import TODAY
from ams_agent.context import Context
from ams_agent.db import connect


def _days(value: float) -> int | float:
    """7.0 -> 7, 0.5 -> 0.5: whole days read as whole numbers."""
    return int(value) if float(value).is_integer() else value


@tool
def get_leave_balance(runtime: ToolRuntime[Context]) -> str:
    """Get the signed-in employee's leave balance for this year.

    For each leave type (annual, sick and casual in India; pto, sick and
    floating in the US): days entitled, carried over from last year,
    used, pending approval, and available to book now.
    """
    with closing(connect()) as con:
        rows = con.execute(
            "SELECT leave_type, entitled_days, carried_over_days,"
            " used_days, pending_days FROM leave_balances"
            " WHERE employee_id = ? AND leave_year = ?",
            (runtime.context.employee_id, TODAY.year),
        ).fetchall()
    if not rows:
        return json.dumps({"error": f"no leave balance for {TODAY.year}"})
    return json.dumps([
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
    ])


TOOLS = [get_leave_balance]
