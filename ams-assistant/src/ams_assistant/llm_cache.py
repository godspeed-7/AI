"""LLM reply cache: the same prompt to the same model returns the saved
reply instead of calling the model again.

In:  passed as cache=get_llm_cache(model, temperature) to the chat
     models in llm.py, rewriter.py and decomposer.py.
Out: LangChain calls lookup() before every LLM call and update() after
     a real one; replies are saved in LLM_CACHE_FILE.

Strategy: our models run at temperature 0, so the same prompt gives the
same reply. The key is the model name + temperature (given when the
cache is made) + LangChain's llm_string (the output format, e.g. the
judge's JSON schema) + the full prompt (question + chunks + template),
so the answer eval only calls the LLM for questions whose prompt
changed. Same idea as reranker.py's score cache. (langchain-community
has a ready SQLiteCache; this avoids installing it.)

Caveats:
- LangChain's llm_string for ChatOllama leaves out the model and the
  temperature ([('_type', 'chat-ollama'), ('stop', None)]), so they
  must be passed in: a cache keyed by llm_string alone handed
  gemma3:4b's replies to gemma3:12b (found 2026-11-06; the cache was
  started fresh then).
- Clears itself when a prompt, the chunks, the model name or the
  temperature changes (new key). Delete LLM_CACHE_FILE by hand when a
  model changes under the same name (e.g. `ollama pull gemma3:4b`
  fetched new weights), or another ChatOllama setting changes.
- It freezes the first reply: to see how much an answer varies between
  runs, delete the file first.
- The time limit and retries (WAIT_SETTINGS) are left out of the key:
  they change how long we wait, not what the model says. (Until
  2026-11-10 they were in it, so replies saved before then are missed
  once.) So is the judge's reply cap (CAP_SETTINGS, 2026-11-14), so
  its saved grades stay valid.
"""

import hashlib
import json
import sqlite3
import threading
import warnings
from collections.abc import Sequence
from functools import cache

from langchain_core._api import LangChainBetaWarning
from langchain_core.caches import BaseCache
from langchain_core.load import dumps, loads
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation
from pydantic import BaseModel

from ams_assistant.config import LLM_CACHE_FILE

# The answer eval calls the LLM from several threads (--workers); one
# connection is shared by every model's cache, so only one thread uses
# it at a time.
db_lock = threading.Lock()


@cache
def get_db() -> sqlite3.Connection:
    """Open the reply table (created on first use)."""
    LLM_CACHE_FILE.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(LLM_CACHE_FILE, check_same_thread=False)
    db.execute("CREATE TABLE IF NOT EXISTS replies "
               "(key TEXT PRIMARY KEY, reply TEXT)")
    return db


def plain(generation: Generation) -> Generation:
    """A copy dumps() can save in full. The OpenAI client (the NVIDIA
    judge) attaches the parsed Scores object to the reply as
    additional_kwargs["parsed"]; dumps() can't save that object, but
    LangChain accepts the same data as a dict, so store it as one."""
    message = getattr(generation, "message", None)
    if message is None:
        return generation
    kwargs = {key: value.model_dump() if isinstance(value, BaseModel)
              else value
              for key, value in message.additional_kwargs.items()}
    if kwargs == message.additional_kwargs:
        return generation
    return generation.model_copy(update={
        "message": message.model_copy(update={"additional_kwargs": kwargs}),
    })


# Model settings that change how long we wait, not the reply.
WAIT_SETTINGS = ("timeout", "request_timeout", "max_retries", "retries")
# The reply cap (judge.py): a reply shorter than it is the same with or
# without it, and one cut off by it fails before it's saved.
CAP_SETTINGS = ("max_tokens",)


def reply_settings(llm_string: str) -> str:
    """LangChain's llm_string without WAIT_SETTINGS and CAP_SETTINGS.
    The hosted models' is '<the model as JSON>---<call options>'; any
    other (ChatOllama's has no JSON part) is returned as it is."""
    model_json, separator, options = llm_string.partition("---")
    try:
        model = json.loads(model_json)
    except ValueError:
        return llm_string
    settings = model.get("kwargs") if isinstance(model, dict) else None
    if not isinstance(settings, dict):
        return llm_string
    for name in WAIT_SETTINGS + CAP_SETTINGS:
        settings.pop(name, None)
    return json.dumps(model, sort_keys=True) + separator + options


class SQLiteLLMCache(BaseCache):
    """BaseCache (LangChain's cache interface) for one model + setting,
    stored in one SQLite table: key -> the reply, serialized with
    LangChain's dumps()."""

    def __init__(self, model: str, temperature: float) -> None:
        self.model_settings = f"{model} temperature={temperature}"

    def key(self, prompt: str, llm_string: str) -> str:
        """A short fingerprint (SHA-256) of the model, the settings that
        shape its reply, and the prompt."""
        text = (f"{self.model_settings}\n{reply_settings(llm_string)}\n"
                f"{prompt}")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def lookup(self, prompt: str,
               llm_string: str) -> Sequence[Generation] | None:
        """The saved reply, or None (LangChain then calls the model)."""
        with db_lock:
            row = get_db().execute(
                "SELECT reply FROM replies WHERE key = ?",
                (self.key(prompt, llm_string),),
            ).fetchone()
        if not row:
            return None
        # loads() is marked beta; that notice would print on every hit.
        # Only the two classes a chat reply is made of may be rebuilt.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LangChainBetaWarning)
            try:
                return loads(row[0],
                             allowed_objects=[ChatGeneration, AIMessage])
            except Exception:
                # A reply saved in a form that can't be rebuilt: call
                # the model again (update() then overwrites the row).
                return None

    def update(self, prompt: str, llm_string: str,
               return_val: Sequence[Generation]) -> None:
        """Save a reply the model just gave."""
        reply = dumps([plain(generation) for generation in return_val])
        with db_lock:
            db = get_db()
            db.execute(
                "INSERT OR REPLACE INTO replies VALUES (?, ?)",
                (self.key(prompt, llm_string), reply),
            )
            db.commit()

    def clear(self, **kwargs) -> None:
        """Delete every saved reply (of every model)."""
        with db_lock:
            db = get_db()
            db.execute("DELETE FROM replies")
            db.commit()


# @cache returns the same object for the same model and temperature.
@cache
def get_llm_cache(model: str, temperature: float) -> SQLiteLLMCache:
    """The reply cache for one model at one temperature."""
    return SQLiteLLMCache(model, temperature)
