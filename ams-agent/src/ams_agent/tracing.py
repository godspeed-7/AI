"""Traces of the runs worth keeping, in our local Langfuse.

In:  run_config(employee_id, chat_id, traced, ...) for each agent run
     (app.py, run_evals.py); TRACE_APP, TRACE_FULL_EVALS, LANGFUSE_URL
     and each job's price (config.py); the LANGFUSE_* keys (environment).
Out: the run's config: the chat ID always; when traced, the Langfuse
     handler that records the run (each model and tool call, time,
     tokens, cost) with user = employee ID, a session and tags.
     session_url(id): a link to a session; flush(): send what's queued;
     sync_prices(): each job's price from config.py into Langfuse
     (`uv run python -m ams_agent.tracing`).

Strategy: two doors trace, the app and the eval runner on a full run;
anything else that builds the agent (quick --only runs, the checks,
scripts) passes no handler, so it sends nothing, and Langfuse's views
hold no test noise. Cost = tokens x the price Langfuse holds for the
model; ours come from config.py, so one place sets them. Labels: the
employee ID, never a name. Our local Langfuse only: traces hold HR data.

Caveats: if Langfuse is down, runs go untraced (never stopped). Cost is
worked out when a trace arrives: a price changed later leaves old
traces as they were. The bill itself is the provider's.
"""

import logging
import re
from functools import cache

from ams_agent.config import JOBS, LANGFUSE_URL

log = logging.getLogger(__name__)


@cache
def client():
    """The Langfuse client, or None if it can't be reached."""
    try:
        from langfuse import Langfuse, is_langfuse_span
        # Only our handler's records: the Anthropic SDK reports each call
        # too (OpenTelemetry), which would count every call twice.
        langfuse = Langfuse(base_url=LANGFUSE_URL,
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
def handler():
    """One Langfuse handler per process, or None."""
    if client() is None:
        return None
    from langfuse.langchain import CallbackHandler
    return CallbackHandler()


def run_config(employee_id: str, chat_id: str, traced: bool = False,
               session: str | None = None, tags: tuple = (),
               name: str | None = None) -> dict:
    """The run's config: the chat ID always; when traced, the handler,
    with the session (the chat, unless given), tags and a trace name."""
    config = {"configurable": {"thread_id": chat_id}}
    if traced and (listener := handler()):
        config |= {"callbacks": [listener],
                   "metadata": {"langfuse_user_id": employee_id,
                                "langfuse_session_id": session or chat_id,
                                "langfuse_tags": list(tags)}}
        if name:  # the trace's name in Langfuse, e.g. "Q21"
            config["run_name"] = name
            config["metadata"]["langfuse_trace_name"] = name
    return config


def session_url(session_id: str) -> str | None:
    """A session's page in Langfuse, or None."""
    if (langfuse := client()) is None:
        return None
    try:
        project = langfuse.api.projects.get().data[0].id
    except Exception:  # noqa: BLE001
        return None
    return f"{LANGFUSE_URL}/project/{project}/sessions/{session_id}"


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
