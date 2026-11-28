"""Sends app questions and full eval runs to our local Langfuse.

In:  run_config(employee_id, chat_id, traced, ...) for each agent run.
Out: the run's config (with a Langfuse handler when traced); score(),
     unscore(), flush(); sync_prices() (`python -m ams_agent.tracing`).

How: our Handler sets step types (STEP_TYPES) and hides counter checks
(QUIET_STEPS); anything not traced sends nothing.

Watch out: Langfuse down = runs untraced, never an error.
"""

import logging
import re
from functools import cache

from langfuse import Langfuse, is_langfuse_span
from langfuse.langchain import CallbackHandler
from langfuse.langchain.CallbackHandler import LANGSMITH_TAG_HIDDEN

from ams_agent.config import (
    JOBS,
    LANGFUSE_URL,
    TRACE_ENVIRONMENT,
    TRACE_NAME,
)

log = logging.getLogger(__name__)

# The type Langfuse shows for each agent step, by its name in the graph
# (a middleware hook is "Class.hook"). Any other step is a chain; model
# and tool calls keep the handler's own types (generation, tool).
STEP_TYPES = {
    TRACE_NAME: "agent",
    "TopicGuard.before_agent": "guardrail",
    "PromptLeakCheck.after_agent": "guardrail",
    "AnswerReview.after_model": "evaluator",
}


# Steps that only check a counter (or reset one, or parse a verdict the
# step above already shows): level DEBUG, which Langfuse's trace view
# hides by default (Min Level). Still recorded: Min Level DEBUG shows
# them. A brake that stops a run still shows in the answer and, in the
# app, in the "budget" score.
QUIET_STEPS = {
    "RunBudget.before_agent", "RunBudget.before_model",
    "RunBudget.after_model", "ModelCallBudget.before_model",
    "ModelCallBudget.after_model", "ToolCallLimitMiddleware.after_model",
    "AnswerReview.before_agent", "PydanticToolsParser",
}


class Handler(CallbackHandler):
    """Langfuse's LangChain handler, with our steps' types and levels."""

    def on_chain_start(self, serialized, inputs, *, run_id,
                       parent_run_id=None, tags=None, metadata=None,
                       **kwargs):
        # LangChain's "hidden" tag: the handler records the step as DEBUG.
        if self.get_langchain_run_name(serialized, **kwargs) in QUIET_STEPS:
            tags = [*(tags or []), LANGSMITH_TAG_HIDDEN]
        return super().on_chain_start(
            serialized, inputs, run_id=run_id, parent_run_id=parent_run_id,
            tags=tags, metadata=metadata, **kwargs)

    def _get_observation_type_from_serialized(self, serialized,
                                              callback_type, **kwargs):
        if callback_type == "chain":
            name = self.get_langchain_run_name(serialized, **kwargs)
            return STEP_TYPES.get(name, "chain")
        return super()._get_observation_type_from_serialized(
            serialized, callback_type, **kwargs)


@cache
def client():
    """The Langfuse client, or None if it can't be reached."""
    try:
        # Only our handler's records: the Anthropic SDK reports each call
        # too (OpenTelemetry), which would count every call twice.
        langfuse = Langfuse(base_url=LANGFUSE_URL,
                            environment=TRACE_ENVIRONMENT,
                            should_export_span=is_langfuse_span)
        if langfuse.auth_check():
            return langfuse
        log.warning("Langfuse refused the keys: runs are not traced")
    # Tracing must never stop a run: without it, runs go untraced.
    except Exception as e:  # noqa: BLE001
        log.warning("Langfuse unavailable (%s): runs are not traced",
                    type(e).__name__)
    return None


@cache
def shared_handler() -> Handler:
    """One handler for the runs without a trace ID of their own: an
    experiment's, each inside its item's trace."""
    return Handler()


def new_trace_id() -> str:
    """A trace's ID, made before the run, so scores can follow it."""
    return Langfuse.create_trace_id()


def run_config(employee_id: str, chat_id: str, traced: bool = False,
               session: str | None = None, tags: tuple = (),
               trace_id: str | None = None) -> dict:
    """The run's config: the chat ID always; when traced, a handler that
    records it as TRACE_NAME, in trace_id if given (a booking resumed
    with the same ID stays one trace), with the session if given."""
    config = {"configurable": {"thread_id": chat_id}}
    if not traced or client() is None:
        return config
    listener = (Handler(trace_context={"trace_id": trace_id}) if trace_id
                else shared_handler())
    metadata = {"langfuse_user_id": employee_id,
                "langfuse_tags": list(tags),
                "langfuse_trace_name": TRACE_NAME}
    if session:
        metadata["langfuse_session_id"] = session
    return config | {"callbacks": [listener], "run_name": TRACE_NAME,
                     "metadata": metadata}


def score(trace_id: str | None, name: str, value: int, comment: str = "",
          score_id: str | None = None) -> None:
    """A yes / no score (1 / 0) on a trace. Sent again with the same
    score_id, it replaces the last. Never stops the app."""
    if not trace_id or (langfuse := client()) is None:
        return
    try:
        langfuse.create_score(trace_id=trace_id, name=name, value=value,
                              data_type="BOOLEAN", comment=comment or None,
                              score_id=score_id)
    except Exception as e:  # noqa: BLE001
        log.warning("score %s not sent (%s)", name, type(e).__name__)


def unscore(score_id: str) -> None:
    """Take a score back (e.g. a thumb un-clicked)."""
    if (langfuse := client()) is None:
        return
    try:
        langfuse.api.scores.delete(score_id)
    except Exception as e:  # noqa: BLE001
        log.warning("score not deleted (%s)", type(e).__name__)


def flush() -> None:
    """Send every queued trace now (before a run's process ends)."""
    if (langfuse := client()) is not None:
        langfuse.flush()


def price_pattern(name: str) -> str:
    """Matches the name, with or without a provider prefix ("google/")
    or a date suffix ("-20261008")."""
    return f"(?i)^([a-z0-9-]+/)?{re.escape(name)}(-[0-9]{{8}})?$"


def per_token(price) -> dict[str, float]:
    """A config Price as Langfuse's prices per token, by usage type. For
    a cached Claude prompt the handler records Anthropic's own names:
    cache_read_input_tokens (read back) and cache_creation_input_tokens
    (written); "input" is the rest. A type without a price costs
    nothing. The written tokens also appear as
    cache_creation_ephemeral_5m_input_tokens: unpriced, or they would
    count twice."""
    def each(per_million: float) -> float:
        return round(per_million / 1e6, 15)  # 1e-07, not 1.00...01e-07

    prices = {"input": each(price.input), "output": each(price.output)}
    if price.cache_read is not None:
        prices["cache_read_input_tokens"] = each(price.cache_read)
    if price.cache_write is not None:
        prices["cache_creation_input_tokens"] = each(price.cache_write)
    return prices


def sync_prices() -> list[str]:
    """Put each job's price from config.py into Langfuse, as the
    project's own model definitions (they win over Langfuse's list)."""
    langfuse = client()
    if langfuse is None:
        raise SystemExit(f"Langfuse isn't reachable at {LANGFUSE_URL}")
    ours, page = {}, 1
    while True:
        found = langfuse.api.models.list(page=page, limit=100)
        ours |= {m.model_name: m for m in found.data
                 if not m.is_langfuse_managed}
        if page >= found.meta.total_pages:
            break
        page += 1
    prices = {model.name: model.price for model, _ in JOBS.values()
              if model.price is not None}
    done = []
    for name, price in prices.items():
        want = per_token(price)
        have = ours.get(name)
        if have and {k: p.price for k, p in (have.prices or {}).items()
                     } == want:
            done.append(f"{name}: up to date")
            continue
        if have:  # a definition can't be edited: replace it
            langfuse.api.models.delete(have.id)
        langfuse.api.models.create(
            model_name=name, match_pattern=price_pattern(name),
            unit="TOKENS", pricing_tiers=[{
                "name": "Standard", "isDefault": True, "priority": 0,
                "conditions": [], "prices": want}])
        cached = (f", cached ${price.cache_read:g}" if price.cache_read
                  is not None else "")
        done.append(f"{name}: ${price.input:g} / ${price.output:g}{cached}"
                    " per 1M tokens in / out")
    return done


if __name__ == "__main__":
    print("\n".join(sync_prices()))
