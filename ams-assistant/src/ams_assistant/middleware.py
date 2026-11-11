"""Our own middleware: code that runs around the agent's calls (stage E).

In:  what LangChain hands a hook: a failed tool call (the exception
     and the request), a model call, or the run so far (state).
Out: what goes back into the run instead, e.g. tool_failed()'s text
     as the tool's result, or a note that sends the model back.

Strategy: build_agent() (agent.py) lists the middleware, ready-made
and ours. ToolErrorMiddleware calls tool_failed() when a tool fails
while running: the model gets a fixed "couldn't check this" note and
answers the rest. ModelFallbackMiddleware logs nothing, so
log_model_failure, inside it, logs each model's failure.
answer_check() sends an empty reply ("_") back to the model once,
then answers CANT_ANSWER. Details go to the log.

Caveats:
- Bad tool inputs never reach tool_failed(): LangChain returns them
  to the model before the tool runs.
- The order of the list matters; see agent_middleware() (agent.py).
"""

import logging
from collections.abc import Callable

from langchain.agents.middleware import (
    AgentState,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    after_model,
    wrap_model_call,
)
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# What the person sees when there's no answer to give: here, and when a
# run fails in the app. The details go to the log, never to the page.
CANT_ANSWER = ("Sorry, I couldn't answer that right now. Please try "
               "again in a moment.")
# answer_check()'s note to the model; also how it knows it already
# asked once.
ASK_AGAIN = "Your last reply was empty. Please answer the question."


def tool_failed(error: Exception, request: ToolCallRequest) -> str:
    """For ToolErrorMiddleware: log a tool that failed while running,
    and return what the model gets as its result. Any error: the text
    is fixed and never includes the error, so no SQL, file path or
    stack trace reaches the model or the person."""
    name = request.tool_call["name"]
    logger.exception("Tool %s failed", name, exc_info=error)
    return (f"Error: {name} couldn't run (a system problem, not the "
            "question). Tell them you couldn't check this right now; "
            "don't guess it, and don't try it again.")


@wrap_model_call
def log_model_failure(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    """Log a model call that failed (after the model's own retries),
    then let the error go on, to the fallback or the front end."""
    try:
        return handler(request)
    except GraphBubbleUp:  # LangGraph's own signals (e.g. a pause)
        raise
    except Exception:
        name = getattr(request.model, "model", type(request.model).__name__)
        logger.exception("Model %s failed", name)
        raise


def is_empty(reply: AIMessage) -> bool:
    """An answer with no letter or digit at all: "", "_", "...".
    (Not "too short": "5" or "No" can be real answers.)"""
    return (not reply.tool_calls
            and not any(char.isalnum() for char in reply.text))


def asked_again(messages: list[AnyMessage]) -> bool:
    """Has answer_check already asked for this question? The last human
    message is either its note or the person's question."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content == ASK_AGAIN
    return False


# can_jump_to: this hook may send the run back to the model.
@after_model(can_jump_to=["model"])
def answer_check(state: AgentState, runtime: Runtime) -> dict | None:
    """An empty answer (Gemini once replied just "_"): ask the model
    again, once, with a note (a new request, so the reply cache can't
    hand back the same "_"); still empty → CANT_ANSWER."""
    reply = state["messages"][-1]
    if not isinstance(reply, AIMessage) or not is_empty(reply):
        return None
    if asked_again(state["messages"]):
        logger.warning("Empty reply again (%r): no answer", reply.text)
        return {"messages": [AIMessage(CANT_ANSWER)]}
    logger.warning("Empty reply (%r): asking the model again", reply.text)
    return {"messages": [HumanMessage(ASK_AGAIN)], "jump_to": "model"}
