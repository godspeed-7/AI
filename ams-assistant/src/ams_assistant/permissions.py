"""Permissions: who may see which HR records (stage D, permission check).

In:  who is asking (the signed-in employee) and the employee row they
     ask about (its employee_id and manager_id).
Out: access() -> "self", "manager" or None; hr_access() -> "hr" or
     None; may_read() and manager_view() say what a level may see.

Strategy: the rule lives here, in code, once. Tools check it before
reading anything; the model never decides who may see what, so the
answer is the same for every model and every wording. Levels:
- "self": all of your own records;
- "manager": the person reports to you: their job, status and key
  dates (probation end, last working day), as in get_my_team; not
  their leave or expense claims;
- "hr": you work in People Operations: everyone's profile, leave and
  expense claims, for the year-end review (year_end_tools.py,
  DEEP_AGENTS_PLAYBOOK.md stage A);
- None: nothing.
Deciding a leave request (approve or reject) is a separate rule,
may_decide(): only the request's approver, never on your own request.

Caveats:
- Direct reports only, not their teams in turn.
- Callers answer NOT_ALLOWED for unknown names too, so the agent can't
  be used to find out who works at AMS.
- "hr" is checked only by the year-end tools: in the chat, People
  Operations staff see what anyone sees. It goes by department, where
  a real company would grant it per role.
"""

from typing import Literal

Access = Literal["self", "manager", "hr"]

# The department whose staff get the "hr" level.
HR_DEPARTMENT = "People Operations"

# What each level may read: tools name their record type.
CAN_READ: dict[Access, set[str]] = {
    "self": {"profile", "leave", "expenses"},
    "manager": {"profile"},
    "hr": {"profile", "leave", "expenses"},
}

# The profile fields a manager sees about a direct report.
MANAGER_FIELDS = ("employee_id", "name", "job_title", "office", "status",
                  "probation_end_date", "last_working_day")

# The tool result for every refusal; it also tells the model how to ask
# for the person's own records.
NOT_ALLOWED = {
    "error": "Not allowed: you can see your own records (leave out "
             "`employee`), and the job, status and key dates of the "
             "people who report to you.",
}


def access(viewer_id: str, subject: dict) -> Access | None:
    """The viewer's access to `subject` (an employees row)."""
    if subject["employee_id"] == viewer_id:
        return "self"
    if subject.get("manager_id") == viewer_id:
        return "manager"
    return None


def hr_access(viewer: dict) -> Access | None:
    """"hr" if the viewer (an employees row) works in People
    Operations; else None."""
    return "hr" if viewer.get("department") == HR_DEPARTMENT else None


def may_read(level: Access | None, record: str) -> bool:
    """May someone with `level` read `record` ("profile", "leave" or
    "expenses")?"""
    return level is not None and record in CAN_READ[level]


def manager_view(profile: dict) -> dict:
    """The part of a direct report's profile their manager may see; the
    probation end date only while on probation."""
    view = {key: profile[key] for key in MANAGER_FIELDS if key in profile}
    if view.get("status") != "probation":
        view.pop("probation_end_date", None)
    return view


def may_decide(viewer_id: str, request: dict) -> bool:
    """May the viewer approve or reject this leave request (a
    leave_requests row)? Only its approver (their manager), and never
    their own request."""
    return (request["approver_id"] == viewer_id
            and request["employee_id"] != viewer_id)
