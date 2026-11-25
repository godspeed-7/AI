"""The AMS agent: Gemini + the tools + short instructions, in a loop.

In:  build_agent(); then agent.invoke({"messages": [...]},
     context=Context(employee_id)) or agent.stream(...) the same way.
Out: the run's messages: the model's tool calls, the tool results and,
     last, the answer (final_answer() picks it out).

Strategy: create_agent runs the agent loop (ReAct): the model either
asks for tools, whose results go back to it, or writes the answer,
which ends the run. ModelCallLimitMiddleware stops it after
MAX_MODEL_CALLS model calls (the step limit). The instructions say:
answer only from tool results, else say you don't know (grounded
answers).

Caveats: no memory of its own; the caller sends the chat's earlier
messages with each question (app.py, run_evals.py).
"""

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.messages import AIMessage, AnyMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from ams_agent.config import (
    AGENT_MODEL,
    AGENT_RETRIES,
    AGENT_TIMEOUT,
    MAX_MODEL_CALLS,
    TODAY,
)
from ams_agent.context import Context
from ams_agent.tools import TOOLS

SYSTEM_PROMPT = f"""\
You are the AMS HR assistant. You help the signed-in employee with \
questions about their own HR records.
Today is {TODAY.day} {TODAY:%B %Y}.
Answer only from what your tools return. If they don't give you the \
answer, say you don't know and suggest asking their manager or People \
Operations; never guess.
Keep answers short and give the numbers."""


def build_agent():
    """The agent, ready to invoke or stream."""
    model = ChatGoogleGenerativeAI(
        model=AGENT_MODEL, timeout=AGENT_TIMEOUT, max_retries=AGENT_RETRIES)
    return create_agent(
        model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        context_schema=Context,
        middleware=[ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS)],
    )


def final_answer(messages: list[AnyMessage]) -> str:
    """The text of the last model message: the agent's answer."""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.text.strip():
            return message.text.strip()
    return ""
