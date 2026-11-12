"""Langfuse tracing: the config that records an agent run there
(EVAL_PLAYBOOK.md, stage A).

In:  who is asking, where it runs ("app", "chat", "eval"), and
     optionally the chat (thread, session), a trace name and tags;
     LANGFUSE_TRACING (config.py) and the LANGFUSE_* keys (~/.zshrc).
Out: run_config(...) -> the config for agent.stream(): the thread_id
     and, when tracing is on, Langfuse's listener and the run's labels.

Strategy: LangChain calls every callback in a run's config at each
step (model calls, tools, the handbook search inside a tool), so one
CallbackHandler records the whole run. LangSmith works the same way,
built into LangChain. The labels travel in the config's metadata
(langfuse_user_id, ...); the code version (git commit) is the
client's release. Langfuse is checked once per process: if it doesn't
answer, the process runs untraced, with one warning.

Caveats:
- Traces hold HR data: our local Langfuse only (~/langfuse); the user
  label is the employee ID, never a name.
- A pause (Confirm?) ends a run: the reply starts a second trace, in
  the same session.
- The agent eval's judge isn't traced (stage B).
"""

import logging
import subprocess
from functools import cache

import httpx
from langfuse import Langfuse
from langfuse.api.core import ApiError
from langfuse.langchain import CallbackHandler

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
