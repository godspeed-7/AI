"""The year-end review: a deep agent that writes People Operations one
leave memo per department (DEEP_AGENTS_PLAYBOOK.md, stage A).

In:  a People Operations employee's ID and the departments to review.
Out: build_year_end_agent(employee_id) -> the agent.
     run_review(employee_id, departments) -> its memos (files in the
     run's state, /memos/<department>.md) and what the run took: model
     calls, prompt tokens per call, tool calls, seconds.
     check_memo(memo, department, seen) -> each person's line checked
     against the records.

Strategy: create_deep_agent (deepagents) on the agent's Gemini model,
with the year-end tool, our call limit and tool-error middleware, and
HRContext for who is asking. Stage A is the baseline later stages are
measured against: no helpers of ours, no to-do list (planning is
opt-in since deepagents 0.7), every department in one conversation.
The memo's format is fixed, so code can check each person's numbers.

Caveats:
- The harness adds a general-purpose helper with all the lead's tools;
  the instructions ask the lead to work alone.
- The memos live in the run's state, in memory: gone when the run ends
  unless taken from its result (stage D: a workspace).
- No checkpointer and no approval yet (stage F): nothing is sent.
- No fallback model: a run's memos are one model's (as in the evals).
"""

import re
import time
from collections.abc import Callable

from deepagents import create_deep_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolErrorMiddleware,
)
from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    ToolMessage,
)

from ams_assistant.agent import agent_llm, long_date
from ams_assistant.config import (
    AGENT_MODEL,
    AGENT_PROVIDER,
    AGENT_THINKING,
    TODAY,
    YEAR_END_MAX_CALLS,
)
from ams_assistant.hr_tools import HRContext, get_employee_card
from ams_assistant.middleware import tool_failed
from ams_assistant.number_check import invented_numbers
from ams_assistant.permissions import hr_access
from ams_assistant.tracing import run_config
from ams_assistant.year_end_tools import department_review, year_end_leave

YEAR_END_PROMPT = """\
You prepare People Operations' year-end leave review at AMS for \
{name} ({employee_id}), People Operations. Today is {today}.

For each department you are asked to review:
1. Call year_end_leave for the department.
2. Write a memo for the department head with write_file, to \
/memos/<department>.md: the department in lower case, spaces as \
hyphens (e.g. /memos/it-and-security.md). Use exactly this format:

# Year-end leave review: <department>
For: <head>

If no more leave is taken before 31 December and every pending \
request is approved:
- <employee>: <days lost> days lost on 31 December; <days carried> \
carry over, to use by <date>

Leaving before 31 December:
- <employee>: leaves on <date>; unused leave is settled on leaving

Pending requests:
- <request ID>: <employee>, <leave type>, <start date> to <end date>, \
<working days> days, waiting for <approver>

Total: <people losing days> people lose <days lost> days on 31 December.

Write one line for each person who loses days, naming them as the \
tool does ("Varun Malhotra (AMS-1040)"). Leave out the "Leaving" part \
if nobody is leaving; write "None" under "Pending requests" if there \
are none. Use the tool's numbers exactly as they are; never add up or \
work out a number yourself. Do the work yourself, one department at a \
time; don't hand it to a helper.
3. When every memo is written, reply with one line per department: \
its memo's path and its total line."""


def memo_path(department: str) -> str:
    """'IT and Security' -> '/memos/it-and-security.md'."""
    return f"/memos/{department.lower().replace(' ', '-')}.md"


def year_end_prompt(card: dict) -> str:
    """The lead's instructions, for the HR person `card` describes."""
    return YEAR_END_PROMPT.format(name=card["name"],
                                  employee_id=card["employee_id"],
                                  today=long_date(TODAY))


def hr_card(employee_id: str) -> dict:
    """Their sign-in card; ValueError if unknown, PermissionError if
    they aren't People Operations (the tool checks again)."""
    card = get_employee_card(employee_id)
    if card is None:
        raise ValueError(f"No employee with ID {employee_id}")
    if hr_access(card) is None:
        raise PermissionError("The year-end review is for People "
                              "Operations only.")
    return card


def build_year_end_agent(employee_id: str, provider: str = AGENT_PROVIDER,
                         model: str = AGENT_MODEL,
                         thinking: bool | None = AGENT_THINKING,
                         cached: bool = True):
    """The lead agent, for People Operations employee `employee_id`.
    cached=False: its model calls skip the reply cache."""
    card = hr_card(employee_id)
    return create_deep_agent(
        model=agent_llm(provider, model, thinking, cached),
        tools=[year_end_leave],
        system_prompt=year_end_prompt(card),
        # Every run passes context=HRContext(...): who is asking, for
        # the tool's permission check, from code, never the model.
        context_schema=HRContext,
        middleware=[
            # A loop stops here; "error" raises, so the caller words it.
            ModelCallLimitMiddleware(run_limit=YEAR_END_MAX_CALLS,
                                     exit_behavior="error"),
            # A tool that fails: "couldn't check", never the error.
            ToolErrorMiddleware(on_error=tool_failed),
        ],
        name="year-end-lead",
    )


def run_review(employee_id: str, departments: list[str], *,
               on_message: Callable[[AnyMessage], None] | None = None,
               cached: bool = True) -> dict:
    """Run the review of `departments` as `employee_id`; on_message(m)
    sees each new message as it comes. Returns the memos, the lead's
    last reply, what the run took and all it saw (for the number
    check)."""
    card = hr_card(employee_id)
    agent = build_year_end_agent(employee_id, cached=cached)
    ask = ("Prepare the year-end leave review for: "
           + ", ".join(departments) + ".")
    config = run_config(employee_id, "year-end",
                        trace_name="year-end review",
                        tags=(f"{len(departments)} departments",))
    state: dict = {}
    shown, stopped = 0, None
    start = time.perf_counter()
    try:
        # "values": the whole state after each step; the last one holds
        # every message and the files.
        for state in agent.stream(
                {"messages": [HumanMessage(ask)]},
                context=HRContext(employee_id=employee_id),
                config=config, stream_mode="values"):
            if on_message:
                for message in state["messages"][shown:]:
                    on_message(message)
            shown = len(state["messages"])
    except ModelCallLimitExceededError:
        stopped = f"stopped at the limit of {YEAR_END_MAX_CALLS} model calls"
    seconds = round(time.perf_counter() - start, 1)

    messages = state.get("messages", [])
    replies = [m for m in messages if isinstance(m, AIMessage)]
    results = [m for m in messages if isinstance(m, ToolMessage)]
    usage = [m.usage_metadata or {} for m in replies]
    return {
        "memos": {path: data["content"]
                  for path, data in (state.get("files") or {}).items()},
        "answer": replies[-1].text if replies else "",
        "model_calls": len(replies),
        "prompt_tokens": [u.get("input_tokens", 0) for u in usage],
        "output_tokens": sum(u.get("output_tokens", 0) for u in usage),
        "tool_calls": [c["name"] for m in replies for c in m.tool_calls],
        "seconds": seconds,
        "stopped": stopped,
        # Everything the model saw: its instructions, the ask, every
        # tool result. A memo's numbers must come from here.
        "seen": "\n".join([year_end_prompt(card), ask,
                           *(str(m.content) for m in results)]),
    }


# A number on its own: not the digits of an ID (AMS-1040, LR-0190).
NUMBER = re.compile(r"(?<![\w-])\d+(?:\.\d+)?")


def line_numbers(line: str) -> set[float]:
    """The numbers in a memo line: '9 days lost; 5 carry over' ->
    {9.0, 5.0}."""
    return {float(n) for n in NUMBER.findall(line)}


def check_memo(memo: str, department: str, seen: str) -> dict:
    """Check a department's memo against the records (code, not a
    model): each person who loses days has a line with their ID and
    both their numbers (days lost, days carried over); each person
    leaving has a line saying so; every pending request's ID is there;
    the total line has both totals; and no number is unbacked by what
    the lead saw (number_check.py)."""
    review = department_review(department)
    lines = memo.splitlines()
    right, wrong, missing = [], [], []
    for person in review["people"]:
        employee_id = person["employee"].rsplit("(", 1)[1].rstrip(")")
        # Their line in the right part: an ID shows up elsewhere too
        # (the head on "For:", a pending request).
        if person.get("leaving_on"):
            word = "leav"
        elif person["days_lost_on_31_december"] > 0:
            word = "lost"
        else:
            continue  # loses nothing: not in the memo
        line = next((text for text in lines if employee_id in text
                     and word in text.lower()), None)
        if line is None:
            missing.append(employee_id)
        elif word == "leav" or {
                float(person["days_lost_on_31_december"]),
                float(person["days_carried_into_next_year"]),
        } <= line_numbers(line):
            right.append(employee_id)
        else:
            wrong.append(employee_id)
    pending = [request["request_id"] for person in review["people"]
               for request in person.get("pending_requests", [])]
    totals = review["totals"]
    total_line = next((text for text in lines
                       if text.lower().startswith("total")), "")
    return {
        "right": right,
        "wrong": wrong,
        "missing": missing,
        "pending_missing": [rid for rid in pending if rid not in memo],
        "total_right": {float(totals["people_losing_days"]),
                        float(totals["days_lost_on_31_december"])}
                       <= line_numbers(total_line),
        "invented": invented_numbers(memo, seen),
    }
