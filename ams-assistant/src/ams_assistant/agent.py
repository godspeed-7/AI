"""The HR agent: LangChain's create_agent() with our tools (stage B).

In:  build_agent(employee_id) for the person asking; then run it with
     agent.stream({"messages": [question]}, context=HRContext(id)).
Out: the run's steps; its "messages" hold the whole conversation
     (question, tool calls, tool results, answer).

Strategy: the loop of agent_by_hand.py, run by LangChain (on
LangGraph): model -> tools -> model ... until a reply asks for no
tool. We hand it the model (build_llm), the tools, the instructions
and HRContext; each tool reads who is asking from its runtime. The
instructions carry the person's key facts (about()), read by code
when the agent is built, so the model knows them before it picks a
tool: e.g. that Rahul is on probation, before it searches the rules.

Caveats:
- At most AGENT_MAX_STEPS model calls per question (middleware, stage
  E): one more raises ModelCallLimitExceededError, and each front end
  says it stopped. LangGraph's own recursion_limit counts graph steps,
  and every middleware hook adds one, so it stays at its default.
- A bad tool input (e.g. leave_type="vacation") goes back to the model
  as the tool's result. A tool that fails while running (database or
  Qdrant down) does too, as a fixed "couldn't check this" note
  (middleware.py); in agent_by_hand.py it still stops the run.
- A model call that fails after its retries goes to the fallback model
  (AGENT_FALLBACK_MODEL: Qwen, local, slower), and the failure is
  logged. It tries the main model first on every call.
- An empty answer ("_") goes back to the model once, then becomes
  CANT_ANSWER (middleware.py).
- TRACING (config.py) sends every run to LangSmith.
- The key facts are read once, at sign-in: a change in the database
  shows after signing in again.
"""

import os
import re
from datetime import date

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ToolErrorMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from ams_assistant.config import (
    AGENT_FALLBACK_MODEL,
    AGENT_FALLBACK_PROVIDER,
    AGENT_MAX_STEPS,
    AGENT_MODEL,
    AGENT_PROVIDER,
    AGENT_RETRIES,
    AGENT_THINKING,
    AGENT_TIMEOUT,
    TODAY,
    TRACING,
)
from ams_assistant.hr_tools import (
    HRContext,
    get_employee_card,
    get_expense_claims,
    get_leave_balance,
    get_leave_requests,
    get_my_team,
    get_profile,
    time_since,
)
from ams_assistant.leave_tools import submit_leave_request
from ams_assistant.llm import build_llm
from ams_assistant.middleware import (
    answer_check,
    log_model_failure,
    tool_failed,
)
from ams_assistant.policy_tools import search_policies

if TRACING:
    # LangChain reads this before each run and, when "true", sends the
    # run to LangSmith (config.py). Set here, at import, so the app,
    # chat.py and the evals all follow the one flag.
    os.environ["LANGSMITH_TRACING"] = "true"

# The tools the model may ask for: the HR database (read), the
# handbooks, then the one tool that writes.
AGENT_TOOLS = [
    get_profile,
    get_my_team,
    get_leave_balance,
    get_leave_requests,
    get_expense_claims,
    search_policies,
    submit_leave_request,
]

INSTRUCTIONS = (
    "You are the AMS HR assistant, helping {name}. Today is {today}.\n\n"
    "About {name}, from the HR database:\n{about}\n\n"
    "Use the tools to look up their other records and the company "
    "handbooks. If a tool says something isn't allowed, tell them "
    "plainly. Answer only from these facts and what the tools return; "
    "if they don't cover the question, say you can't tell. When you use "
    "a handbook rule, name its handbook and section. Write dates like 24 "
    "December 2026. Keep answers short."
)


def long_date(day: str | date) -> str:
    """'2027-01-20' -> '20 January 2027', as the answers write dates."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    return day.strftime("%-d %B %Y")  # %-d: no leading zero


def about(card: dict) -> str:
    """The employee's key facts (get_employee_card), one per line: the
    ones handbook rules depend on, such as payroll country, grade,
    status and its dates, and time at AMS."""
    lines = [
        f"- {card['job_title']}, {card['department']} department; "
        f"employee ID {card['employee_id']}",
        f"- office: {card['office']} ({card['payroll']} payroll); "
        f"grade {card['grade']}",
    ]
    if "manager_name" in card:
        lines.append(f"- manager: {card['manager_name']}")
    lines.append(f"- joined {long_date(card['join_date'])} "
                 f"({time_since(card['join_date'])} at AMS)")
    if card["status"] == "probation":
        # The US handbook calls probation the introductory period.
        period = ("in the introductory period (probation)"
                  if card["payroll"] == "US" else "on probation")
        lines.append(f"- status: {period} until "
                     f"{long_date(card['probation_end_date'])}")
    elif card["status"] == "notice_period":
        lines.append(f"- status: on notice: resigned on "
                     f"{long_date(card['resignation_date'])}, last "
                     f"working day {long_date(card['last_working_day'])}")
    else:
        lines.append("- status: confirmed (past probation)")
    if card["direct_reports"]:
        lines.append(f"- manages {card['direct_reports']} direct "
                     f"report{'s' if card['direct_reports'] != 1 else ''}")
    return "\n".join(lines)


def instructions_for(card: dict) -> str:
    """The system message for the employee `card` describes."""
    return INSTRUCTIONS.format(name=card["name"], today=long_date(TODAY),
                               about=about(card))


# Gemma 4's thinking: "<thought>...</thought>", then the reply text.
THOUGHT = re.compile(r"\s*<thought>(.*?)(?:</thought>(.*))?\Z", re.DOTALL)


def split_thinking(reply: AIMessage) -> tuple[str, str]:
    """Split a reply into (thinking, text); thinking is "" if none."""
    # qwen3 (reasoning=True): the thinking comes apart from the text.
    thinking = reply.additional_kwargs.get("reasoning_content", "")
    # .text: the reply's text, whether content is a string (Ollama,
    # ChatOpenAI) or a list of parts (Gemini).
    match = THOUGHT.match(reply.text)
    if match:  # Gemma 4: the thinking is inside the text
        return match.group(1).strip(), (match.group(2) or "").strip()
    return thinking.strip(), reply.text.strip()


def agent_llm(provider: str, model: str,
              thinking: bool | None) -> BaseChatModel:
    """A model for the agent: tools on, and the agent's shorter time
    limit, since someone is waiting (config.py)."""
    return build_llm(provider, model, temperature=0,
                     reasoning=thinking if provider == "ollama" else None,
                     with_tools=True, timeout=AGENT_TIMEOUT,
                     retries=AGENT_RETRIES)


def agent_middleware(provider: str, model: str,
                     fallback: bool) -> list[AgentMiddleware]:
    """The rules around the agent's calls, in order: before hooks run
    first to last, after hooks last to first, and wrap hooks nest (the
    first listed is the outermost)."""
    middleware = [
        # An empty answer ("_") goes back to the model once. First, so
        # its after_model runs last: after the call counter has counted
        # the call (a jump skips the after hooks still to run).
        answer_check,
        # Counts model calls per question (run_limit); "error" raises
        # instead of answering with its own technical text, so each
        # front end words the stop itself.
        ModelCallLimitMiddleware(run_limit=AGENT_MAX_STEPS,
                                 exit_behavior="error"),
        # A tool that fails while running: the model is told it
        # couldn't check, and answers the rest (middleware.py).
        ToolErrorMiddleware(on_error=tool_failed),
    ]
    backup = (AGENT_FALLBACK_PROVIDER, AGENT_FALLBACK_MODEL)
    if fallback and AGENT_FALLBACK_MODEL and (provider, model) != backup:
        middleware += [
            # A model call that fails goes to the backup model...
            ModelFallbackMiddleware(agent_llm(*backup, AGENT_THINKING)),
            # ...and, inside it, each model's failure is logged (the
            # fallback logs nothing).
            log_model_failure,
        ]
    return middleware


def build_agent(employee_id: str, provider: str = AGENT_PROVIDER,
                model: str = AGENT_MODEL,
                thinking: bool | None = AGENT_THINKING,
                fallback: bool = True):
    """Return the agent, ready to run for `employee_id` (ValueError if
    unknown). The model comes from config.py unless given (the evals
    compare others); `thinking` only applies to Ollama models.
    fallback=False: a failed model call stays a failure (the evals)."""
    card = get_employee_card(employee_id)
    if card is None:
        raise ValueError(f"No employee with ID {employee_id}")
    # context_schema: every run must pass context=HRContext(...), and
    # tools get it as runtime.context.
    return create_agent(
        agent_llm(provider, model, thinking),
        tools=AGENT_TOOLS,
        system_prompt=instructions_for(card),
        context_schema=HRContext,
        middleware=agent_middleware(provider, model, fallback),
    )
