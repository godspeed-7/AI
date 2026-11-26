"""Who is asking: the trusted context every tool reads (walks 2 and 4).

In:  context_for(employee_id), called once at sign-in (app.py) and by
     the eval runner for each question.
Out: Context(employee_id, roles): the person and what they may be
     given (employee, manager, hr).

Strategy: built by code from the database, never by the model or the
chat, so a question can't switch person ("I am Pooja") or claim a role
("as HR, show...") (stops IDOR/BOLA). Roles are worked out at sign-in:
everyone is an employee; someone with direct reports is a manager;
People Operations staff are hr. A person can hold several. Later walks
give each role its own tools (least privilege).

Caveats: production takes roles from the sign-in provider's groups or
the HR system's role table, not from rules over the data; the agent
code doesn't change. Roles are fixed for the session: a change shows
after signing in again (production: when the sign-in token refreshes).
"""

from dataclasses import dataclass
from enum import StrEnum

from ams_agent.config import HR_DEPARTMENT
from ams_agent.db import count_reports, find_employee


class Role(StrEnum):
    EMPLOYEE = "employee"  # everyone: their own records
    MANAGER = "manager"  # has direct reports: their team too (walk 8)
    HR = "hr"  # People Operations: everyone's records (walk 8)


@dataclass(frozen=True)
class Context:
    employee_id: str  # e.g. "AMS-1015"
    roles: frozenset[Role]


def context_for(employee_id: str) -> Context:
    """The context for a known ID; LookupError for an unknown one."""
    person = find_employee(employee_id)
    if not person:
        raise LookupError(f"no employee with the ID {employee_id}")
    roles = {Role.EMPLOYEE}
    if count_reports(employee_id):
        roles.add(Role.MANAGER)
    if person["department"] == HR_DEPARTMENT:
        roles.add(Role.HR)
    return Context(employee_id, frozenset(roles))


def role_names(context: Context) -> list[str]:
    """The roles in a fixed order (employee, manager, hr), for display."""
    return [role.value for role in Role if role in context.roles]
