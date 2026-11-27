"""The brakes on the agent loop: a budget per question.

In:  brakes(), put in the agent's middleware first (agent.py).
Out: a run that ends with STOP_REPLY when a budget runs out; the
     reason goes to the log and the message's response_metadata
     ("stopped_by": model_calls, seconds or tokens), never to the person.

Strategy: four budgets in code (OWASP LLM10, unbounded consumption):
- model calls (MAX_MODEL_CALLS): LangChain's ModelCallLimitMiddleware,
  with our reply instead of its own text;
- tool calls (MAX_TOOL_CALLS): ToolCallLimitMiddleware; calls over the
  limit are refused and the model answers with what it has;
- time (MAX_SECONDS; BACKUP_MAX_SECONDS once the slower backup model
  answers or the breaker is open) and tokens (MAX_TOKENS):
  RunBudget, as LangChain has no limit for these. It starts the clock
  before the topic guard, and checks both before every model call.
The counts live in the run's state, so they restart for each question.

Caveats: a check runs between calls, so a slow call still finishes (up
to AGENT.timeout); the topic guard's tokens aren't counted.
"""

import logging
import time
from typing import Annotated, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    hook_config,
)
from langchain.agents.middleware.types import PrivateStateAttr
from langchain.messages import AIMessage
from langgraph.channels.untracked_value import UntrackedValue

from ams_agent.config import (
    BACKUP,
    BACKUP_MAX_SECONDS,
    MAX_MODEL_CALLS,
    MAX_SECONDS,
    MAX_TOKENS,
    MAX_TOOL_CALLS,
)
from ams_agent.resilience import BREAKER, answered_by

log = logging.getLogger(__name__)

STOP_REPLY = ("Sorry, that took too many steps. Please ask again more"
              " simply, or ask People Operations.")
STOP_NAME = "budget"  # marks the stop reply among the messages


def stop(reason: str) -> dict:
    """End the run with the fixed reply; the reason is logged."""
    log.warning("question stopped: %s budget used up", reason)
    reply = AIMessage(STOP_REPLY, name=STOP_NAME,
                      response_metadata={"stopped_by": reason})
    return {"messages": [reply], "jump_to": "end"}


def stopped_by(message) -> str | None:
    """Which budget ended the run, if this is the stop reply."""
    if isinstance(message, AIMessage) and message.name == STOP_NAME:
        return message.response_metadata.get("stopped_by")
    return None


class BudgetState(AgentState):
    # Per run (UntrackedValue), and never in the agent's input or output.
    run_started: NotRequired[Annotated[float, UntrackedValue,
                                       PrivateStateAttr]]
    run_tokens: NotRequired[Annotated[int, UntrackedValue,
                                      PrivateStateAttr]]
    run_backup: NotRequired[Annotated[bool, UntrackedValue,
                                      PrivateStateAttr]]


class RunBudget(AgentMiddleware):
    """Time and tokens for one question."""

    state_schema = BudgetState

    def __init__(self, seconds: float = MAX_SECONDS,
                 tokens: int = MAX_TOKENS, clock=time.monotonic,
                 backup_seconds: float = BACKUP_MAX_SECONDS) -> None:
        super().__init__()
        self.seconds, self.tokens, self.clock = seconds, tokens, clock
        self.backup_seconds = backup_seconds

    def before_agent(self, state, runtime) -> dict:
        return {"run_started": self.clock(), "run_tokens": 0,
                "run_backup": False}

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime) -> dict | None:
        now = self.clock()
        # The slower backup model gets its own, longer time.
        backup = state.get("run_backup") or BREAKER.is_open()
        limit = self.backup_seconds if backup else self.seconds
        if now - state.get("run_started", now) > limit:
            return stop("seconds")
        if state.get("run_tokens", 0) > self.tokens:
            return stop("tokens")
        return None

    def after_model(self, state, runtime) -> dict | None:
        usage = getattr(state["messages"][-1], "usage_metadata", None)
        used = (usage or {}).get("total_tokens", 0)
        backup = answered_by(state["messages"][-1]) == BACKUP.name
        return {"run_tokens": state.get("run_tokens", 0) + used,
                "run_backup": state.get("run_backup", False) or backup}


class ModelCallBudget(ModelCallLimitMiddleware):
    """LangChain's model call limit, ending with our reply."""

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime) -> dict | None:
        if super().before_model(state, runtime):
            return stop("model_calls")
        return None


def brakes() -> list[AgentMiddleware]:
    """The budget middleware, in order; RunBudget first starts the clock."""
    return [
        RunBudget(),
        ModelCallBudget(run_limit=MAX_MODEL_CALLS),
        ToolCallLimitMiddleware(run_limit=MAX_TOOL_CALLS),
    ]
