"""The HR agent: LangChain's create_agent() with our tools (stage B).

In:  build_agent(name) for the person asking; then run it with
     agent.stream({"messages": [question]}, context=HRContext(id)).
Out: the run's steps; its "messages" hold the whole conversation
     (question, tool calls, tool results, answer).

Strategy: the loop of agent_by_hand.py, run by LangChain (on
LangGraph): model -> tools -> model ... until a reply asks for no
tool. We hand it the model (build_llm), the tools, the instructions
and HRContext; each tool reads who is asking from its runtime.

Caveats:
- The step limit is LangGraph's recursion_limit (RECURSION_LIMIT):
  every model reply and every round of tool runs is one step.
- A bad tool input (e.g. leave_type="vacation") goes back to the model
  as the tool's result; any other tool error stops the run, as in
  agent_by_hand.py.
- TRACING (config.py) sends every run to LangSmith.
"""

import os
import re

from langchain.agents import create_agent
from langchain_core.messages import AIMessage

from ams_assistant.config import (
    AGENT_MAX_STEPS,
    AGENT_MODEL,
    AGENT_PROVIDER,
    AGENT_THINKING,
    TODAY,
    TRACING,
)
from ams_assistant.hr_tools import (
    HRContext,
    get_my_expense_claims,
    get_my_leave_balance,
    get_my_leave_requests,
    get_my_profile,
    get_my_team,
)
from ams_assistant.llm import build_llm
from ams_assistant.policy_tools import search_policies

if TRACING:
    # LangChain reads this before each run and, when "true", sends the
    # run to LangSmith (config.py). Set here, at import, so the app,
    # chat.py and the evals all follow the one flag.
    os.environ["LANGSMITH_TRACING"] = "true"

# The tools the model may ask for: the HR database, then the handbooks.
AGENT_TOOLS = [
    get_my_profile,
    get_my_team,
    get_my_leave_balance,
    get_my_leave_requests,
    get_my_expense_claims,
    search_policies,
]

INSTRUCTIONS = (
    "You are the AMS HR assistant, helping {name}. Today is {today}. Use "
    "the tools to look up their records and the company handbooks. "
    "Answer only from what the tools return; if they don't cover the "
    "question, say you can't tell. When you use a handbook rule, name its "
    "handbook and section. Write dates like 24 December 2026. Keep "
    "answers short."
)


def instructions_for(name: str) -> str:
    """The system message for the employee called `name`."""
    # %-d: the day without a leading zero (16 November 2026).
    return INSTRUCTIONS.format(name=name,
                               today=TODAY.strftime("%-d %B %Y"))

# AGENT_MAX_STEPS model replies with a tool round after each, + 1.
RECURSION_LIMIT = 2 * AGENT_MAX_STEPS + 1

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


def build_agent(name: str, provider: str = AGENT_PROVIDER,
                model: str = AGENT_MODEL,
                thinking: bool | None = AGENT_THINKING):
    """Return the agent, ready to run for the employee called `name`.
    The model comes from config.py unless given (the evals compare
    others); `thinking` only applies to Ollama models."""
    llm = build_llm(provider, model, temperature=0,
                    reasoning=thinking if provider == "ollama" else None,
                    with_tools=True)
    # context_schema: every run must pass context=HRContext(...), and
    # tools get it as runtime.context.
    return create_agent(
        llm,
        tools=AGENT_TOOLS,
        system_prompt=instructions_for(name),
        context_schema=HRContext,
    )
