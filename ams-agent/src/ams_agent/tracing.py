"""Traces of every run in our local Langfuse, when switched on (walk 15).

In:  run_config(employee_id, chat_id) for each agent run (app.py);
     TRACING (config.py) and the LANGFUSE_* keys (environment).
Out: the config that records the run (every model and tool call, time,
     tokens, errors) with user = employee ID and session = chat; an
     empty one while TRACING is off.

Strategy: LangChain hands every step to the callbacks in a run's
config, so one Langfuse CallbackHandler records the whole run. Labels:
the employee ID, never a name (names exist only on the screen, walk
13). Our local Langfuse only: traces hold HR data. Retention: set the
project's data retention to 30 days in Langfuse's settings.

Caveats: OFF until switched on (TRACING = True): you asked that test
runs are not logged, so the evals never trace.
"""

import logging
from functools import cache

from ams_agent.config import TRACING

log = logging.getLogger(__name__)


@cache
def handler():
    """One Langfuse handler per process, or None (off, or unreachable)."""
    if not TRACING:
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    # Tracing must never stop the app: without it, runs go untraced.
    except Exception as e:  # noqa: BLE001
        log.warning("Langfuse unavailable (%s): runs are not traced",
                    type(e).__name__)
        return None


def run_config(employee_id: str, chat_id: str) -> dict:
    """The run's config: the chat ID always, tracing when it's on."""
    config = {"configurable": {"thread_id": chat_id}}
    if listener := handler():
        config |= {"callbacks": [listener],
                   "metadata": {"langfuse_user_id": employee_id,
                                "langfuse_session_id": chat_id}}
    return config
