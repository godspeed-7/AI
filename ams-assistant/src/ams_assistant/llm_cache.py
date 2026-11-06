"""LLM reply cache: the same prompt to the same model returns the saved
reply instead of calling Ollama again.

In:  passed as ChatOllama(cache=get_llm_cache()) in chain.py, judge.py
     and rewriter.py.
Out: LangChain calls lookup() before every LLM call and update() after
     a real one; replies are saved in LLM_CACHE_FILE.

Strategy: our models run at temperature 0, so the same prompt gives the
same reply. LangChain builds the key from the full prompt (question +
chunks + template) and the model's settings (name, temperature,
num_ctx, output format), so the answer eval only calls the LLM for
questions whose prompt changed. Same idea as reranker.py's score cache.
(langchain-community has a ready SQLiteCache; this avoids installing
it.)

Caveats:
- Clears itself when a prompt, the chunks or a model setting changes
  (new key). Delete LLM_CACHE_FILE by hand when a model changes under
  the same name (e.g. `ollama pull gemma3:4b` fetched new weights).
- It freezes the first reply: to see how much an answer varies between
  runs, delete the file first.
"""

import hashlib
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

from ams_assistant.config import LLM_CACHE_FILE


class SQLiteLLMCache(BaseCache):
    """BaseCache (LangChain's cache interface) stored in one SQLite
    table: key -> the reply, serialized with LangChain's dumps()."""

    def __init__(self) -> None:
        LLM_CACHE_FILE.parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(LLM_CACHE_FILE, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS replies "
                        "(key TEXT PRIMARY KEY, reply TEXT)")
        # The answer eval calls the LLM from several threads (--workers);
        # one connection is shared, so only one thread uses it at a time.
        self.lock = threading.Lock()

    @staticmethod
    def key(prompt: str, llm_string: str) -> str:
        """A short fingerprint (SHA-256) of the model settings + prompt."""
        text = f"{llm_string}\n{prompt}"
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def lookup(self, prompt: str,
               llm_string: str) -> Sequence[Generation] | None:
        """The saved reply, or None (LangChain then calls the model)."""
        with self.lock:
            row = self.db.execute(
                "SELECT reply FROM replies WHERE key = ?",
                (self.key(prompt, llm_string),),
            ).fetchone()
        if not row:
            return None
        # loads() is marked beta; that notice would print on every hit.
        # Only the two classes a chat reply is made of may be rebuilt.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", LangChainBetaWarning)
            return loads(row[0], allowed_objects=[ChatGeneration, AIMessage])

    def update(self, prompt: str, llm_string: str,
               return_val: Sequence[Generation]) -> None:
        """Save a reply the model just gave."""
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO replies VALUES (?, ?)",
                (self.key(prompt, llm_string), dumps(list(return_val))),
            )
            self.db.commit()

    def clear(self, **kwargs) -> None:
        """Delete every saved reply."""
        with self.lock:
            self.db.execute("DELETE FROM replies")
            self.db.commit()


# One cache for every model and thread: @cache returns the same object
# on every call.
@cache
def get_llm_cache() -> SQLiteLLMCache:
    """Open the cache (created on first use)."""
    return SQLiteLLMCache()
