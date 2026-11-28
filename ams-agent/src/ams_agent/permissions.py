"""Who may see whose records: one check, in code.

In:  the asker's Context and who the question is about (none, ID, name).
Out: target() -> (employee_id, None) or (None, a reply for the model);
     offer_by_role, which hides tools the asker's roles can't use.

How: own records for all, your reports' for managers, everyone's for
hr (Employee 9.5). Not allowed and unknown get the same reply.

Watch out: roles come from sign-in, so "I'm HR now" changes nothing.
"""

import re

from langchain.agents.middleware import ModelRequest, wrap_model_call

from ams_agent.context import Context, Role
from ams_agent.db import find_employee, managers_above, people_named

NOT_ALLOWED = ("Not allowed: you can only see your own records, or those"
               " of people you manage. Nothing was looked up.")
EMPLOYEE_ID = re.compile(r"AMS-\d{4}", re.IGNORECASE)


def may_see(context: Context, employee_id: str) -> bool:
    """True if the asker may see this employee's records."""
    if employee_id == context.employee_id:
        return True
    if not find_employee(employee_id):
        return False
    if Role.HR in context.roles:
        return True
    return (Role.MANAGER in context.roles
            and context.employee_id in managers_above(employee_id))


def target(context: Context, employee: str | None) -> tuple:
    """Whose records a tool may read: (id, None) or (None, reply)."""
    who = (employee or "").strip()
    if not who:
        return context.employee_id, None
    if EMPLOYEE_ID.fullmatch(who):
        found = [who.upper()]
    else:
        found = people_named(who)
    visible = [i for i in found if may_see(context, i)]
    if len(visible) == 1:
        return visible[0], None
    if not visible:
        return None, NOT_ALLOWED
    return None, (f"More than one person matches {who!r}: "
                  f"{', '.join(visible[:10])}. Ask which one, by ID.")


# A tool listed here is offered only to these roles; others go to all.
TOOL_ROLES = {"get_team": {Role.MANAGER}}


@wrap_model_call
def offer_by_role(request: ModelRequest, handler):
    """Before each model call: drop the tools the asker's roles can't use."""
    roles = request.runtime.context.roles
    tools = [t for t in request.tools
             if roles & TOOL_ROLES.get(getattr(t, "name", ""), roles)]
    return handler(request.override(tools=tools))
