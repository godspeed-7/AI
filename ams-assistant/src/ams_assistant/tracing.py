"""Langfuse tracing: the config that records an agent run there
(EVAL_PLAYBOOK.md, stage A).

In:  who is asking, where it runs ("app", "chat", "eval"), and
     optionally the chat (thread, session), a trace name and tags;
     LANGFUSE_TRACING (config.py) and the LANGFUSE_* keys (~/.zshrc).
Out: run_config(...) -> the config for agent.stream(): the thread_id
     and, when tracing is on, Langfuse's listener and the run's labels.
     @traced(name, type): a plain function shown as its own step.

Strategy: LangChain calls every callback in a run's config at each
step it runs (model calls, tools, middleware), so one CallbackHandler
records the whole run. LangSmith works the same way, built into
LangChain. The labels travel in the config's metadata
(langfuse_user_id, ...); the code version (git commit) is the
client's release. Langfuse is checked once per process: if it doesn't
answer, the process runs untraced, with one warning. Plain Python
inside a tool (the handbook search's steps) is invisible to
LangChain: @traced records it, but only inside a traced run, so the
RAG scripts and a run with tracing off never send anything.

Caveats:
- Traces hold HR data: our local Langfuse only (~/langfuse); the user
  label is the employee ID, never a name.
- A pause (Confirm?) ends a run: the reply starts a second trace, in
  the same session.
- The agent eval's judge isn't traced (stage B).
"""

import logging
import subprocess
from collections.abc import Callable
from functools import cache, wraps
from typing import Any

import httpx
from langchain_core.documents import Document
from langfuse import Langfuse, get_client
from langfuse.api.core import ApiError
from langfuse.langchain import CallbackHandler
from opentelemetry import trace

from ams_assistant.config import LANGFUSE_TRACING, PROJECT_ROOT

logger = logging.getLogger(__name__)

START_IT = "start it with: cd ~/langfuse && docker compose up -d"


def code_version() -> str:
    """The git commit the code runs at; "+changes" if edited since."""
    try:
        return subprocess.run(
            ["git", "describe", "--always", "--dirty=+changes"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


@cache
def listener() -> CallbackHandler | None:
    """Langfuse's listener, made once per process; None when tracing is
    off or Langfuse doesn't answer (keys wrong, or not running)."""
    if not LANGFUSE_TRACING:
        return None
    client = Langfuse(release=code_version())
    try:
        ready = client.auth_check()  # False: no keys set
    except httpx.HTTPError:  # not running: the connection fails
        logger.warning("Langfuse isn't answering: this run isn't traced; "
                       "%s", START_IT)
        return None
    except ApiError:  # e.g. 401: wrong keys
        ready = False
    if not ready:
        logger.warning("Langfuse refused the keys (LANGFUSE_* in "
                       "~/.zshrc): this run isn't traced")
        return None
    return CallbackHandler()


def run_config(employee_id: str, source: str, *,
               thread_id: str | None = None,
               session_id: str | None = None,
               trace_name: str = "ams-agent",
               tags: tuple[str, ...] = ()) -> dict:
    """The config for one agent run: the chat's thread_id (its memory)
    and, when tracing is on, Langfuse's listener with the run's labels:
    user = employee_id (never a name), session = the chat, tags = where
    it runs plus `tags`, and the trace's name."""
    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}
    handler = listener()
    if handler is None:
        return config
    config["callbacks"] = [handler]
    config["metadata"] = {
        "langfuse_user_id": employee_id,
        "langfuse_tags": [source, *tags],
        "langfuse_trace_name": trace_name,
    }
    if session_id:
        config["metadata"]["langfuse_session_id"] = session_id
    return config


def traced(name: str, as_type: str = "span", *,
           show_input: Callable[..., Any] | None = None,
           show_output: Callable[[Any], Any] | None = None) -> Callable:
    """Decorator: inside a traced run, each call of the function becomes
    its own step, `name` of type `as_type` ("retriever", "span", ...),
    showing show_input(*args, **kwargs) and show_output(result).
    Outside one (tracing off, or a script with no agent run), the
    function runs as it is and nothing is sent."""
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        def run(*args, **kwargs):
            # A run's steps are OpenTelemetry spans; none is current
            # unless Langfuse's listener is recording this run.
            if not trace.get_current_span().get_span_context().is_valid:
                return function(*args, **kwargs)
            shown_in = show_input(*args, **kwargs) if show_input else None
            with get_client().start_as_current_observation(
                    name=name, as_type=as_type, input=shown_in) as step:
                result = function(*args, **kwargs)
                if show_output:
                    step.update(output=show_output(result))
                return result
        return run
    return decorate


def doc_lines(docs: list[Document]) -> list[str]:
    """How handbook sections show in a trace: one line each, with the
    scores a step gave them (vector, reranker)."""
    lines = []
    for doc in docs:
        meta = doc.metadata
        line = f"{meta.get('source')}#{meta.get('section')}"
        if "score" in meta:
            line += f" · vector {meta['score']:.3f}"
        if "rerank_score" in meta:
            line += f" · reranker {meta['rerank_score']:.2f}"
        lines.append(line)
    return lines
