"""Our own middleware: code that runs around the agent's calls (stages
E and I).

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
then answers CANT_ANSWER. Reflection (stage I): before a final answer
goes out, a checker call (the same model) names a records tool the
answer still needs, from a fixed list, or none; if one, the model is
sent back with a fixed note, once per question. Details go to the log.

Caveats:
- Bad tool inputs never reach tool_failed(): LangChain returns them
  to the model before the tool runs.
- The order of the list matters; see agent_middleware() (agent.py).
- Reflection costs one more model call per answer. The checker sees
  only the latest question, so a follow-up may get a lookup it had a
  turn earlier. A failed check lets the answer go out as it is.
"""

import logging
from collections.abc import Callable
from typing import Literal

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    after_model,
    hook_config,
    wrap_model_call,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool
from langgraph.errors import GraphBubbleUp
from langgraph.runtime import Runtime
from pydantic import Field, create_model

logger = logging.getLogger(__name__)

# What the person sees when there's no answer to give: here, and when a
# run fails in the app. The details go to the log, never to the page.
CANT_ANSWER = ("Sorry, I couldn't answer that right now. Please try "
               "again in a moment.")
# Our notes to the model are human messages (the model reads them as a
# request); their name tells them apart from the person's.
ANSWER_CHECK, REFLECTION = "answer_check", "reflection"
# answer_check()'s note to the model; also how it knows it already
# asked once.
ASK_AGAIN = "Your last reply was empty. Please answer the question."
# Reflection's checker: what it's told, then what it's shown.
CHECK_PROMPT = (
    "You check an HR assistant's draft answer before it is sent. The "
    "assistant can look up the person's own records with these tools:\n"
    "{tools}\n\n"
    "Name the one tool the answer still needs: the question is about "
    "their own records, that tool wasn't used, and the answer asks them "
    "for a fact the tool holds, guesses it, or answers only in general "
    "(e.g. from a handbook). Otherwise answer none."
)
CHECK_INPUT = ("Question: {question}\n\nTools used: {used}\n\n"
               "Draft answer: {answer}")
# Reflection's note to the model, with the tool the checker named.
LOOK_UP = ("Before you answer: you haven't used {tool}. If the question "
           "is about their own records, look them up with it, then "
           "answer again.")


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
    """Has answer_check already asked for this answer? The last human
    message is its note, the reflection's or the person's question."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.name == ANSWER_CHECK
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
    return {"messages": [HumanMessage(ASK_AGAIN, name=ANSWER_CHECK)],
            "jump_to": "model"}


def is_note(message: AnyMessage) -> bool:
    """One of our notes to the model, not the person's words."""
    return (isinstance(message, HumanMessage)
            and message.name in (ANSWER_CHECK, REFLECTION))


def this_turn(messages: list[AnyMessage]) -> tuple[str, list[AnyMessage]]:
    """The person's latest question, and every message after it (the
    model's replies, tool results, our notes)."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, HumanMessage) and not is_note(message):
            return message.text, messages[index + 1:]
    return "", messages


class Reflection(AgentMiddleware):
    """Before a final answer goes out, a checker call names a records
    tool it still needs, or none; if one, the model is sent back with
    LOOK_UP, once per question."""

    def __init__(self, model: BaseChatModel, tools: list[BaseTool],
                 max_calls: int):
        """model: the checker (the agent's own model); tools: the ones
        it may name; max_calls: the agent's model call limit."""
        super().__init__()
        # Fixed choices, never free text: the note is code's, so text
        # in a tool result or the question can't steer the model
        # through the checker; at worst, one needless lookup.
        check = create_model("Check", missing=(
            Literal[("none", *(t.name for t in tools))],
            Field(description="The tool the answer still needs, or none."),
        ))
        # nostream: the app shows the model's tokens as the answer; the
        # checker's aren't.
        self.checker = (model.with_structured_output(check)
                        .with_config(tags=["nostream"]))
        self.prompt = CHECK_PROMPT.format(tools="\n".join(
            f"- {t.name}: {t.description.split('. ')[0]}" for t in tools))
        self.max_calls = max_calls

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: AgentState,
                    runtime: Runtime) -> dict | None:
        reply = state["messages"][-1]
        if (not isinstance(reply, AIMessage) or reply.tool_calls
                or reply.text == CANT_ANSWER):
            return None  # not a final answer
        question, turn = this_turn(state["messages"])
        if any(is_note(m) and m.name == REFLECTION for m in turn):
            return None  # checked once: it goes out as it is
        replies = [m for m in turn if isinstance(m, AIMessage)]
        if len(replies) >= self.max_calls:
            return None  # no model call left to look anything up
        used = sorted({call["name"] for m in replies
                       for call in m.tool_calls})
        try:
            check = self.checker.invoke([
                SystemMessage(self.prompt),
                HumanMessage(CHECK_INPUT.format(
                    question=question, used=", ".join(used) or "none",
                    answer=reply.text)),
            ])
        except Exception:
            logger.exception("Reflection check failed: the answer goes "
                             "out as it is")
            return None
        missing = (None if check.missing == "none" or check.missing in used
                   else check.missing)
        # The app shows it as a step (stream_mode "custom").
        runtime.stream_writer({REFLECTION: missing})
        if missing is None:
            return None
        logger.info("Reflection: the answer still needs %s", missing)
        return {"messages": [HumanMessage(LOOK_UP.format(tool=missing),
                                          name=REFLECTION)],
                "jump_to": "model"}
