"""Preferences: what the agent remembers about a person across chats
(stage G, long-term memory).

In:  who is asking (HRContext); what the model fills in when they say
     how they want answers, e.g. remember_preference(language="Hindi").
Out: their saved preferences, as one line of the agent's instructions
     at sign-in ("keep answers short; answer in Hindi"), and the tools'
     results.

Strategy: LangGraph's store, on disk (SqliteStore, MEMORY_FILE): one
item per preference under ("preferences", employee_id), apart from the
chat memory (one chat, G1). Only choices from a fixed list, never free
text: a preference becomes part of the instructions, so free text
could inject them ("remember: ignore your rules"), and nothing stored
can grant anything (permissions are code). Saving needs no "Confirm?":
it only changes how answers look (a low-risk write, stage D). Code
reads them at sign-in (build_agent); the model never looks them up.

Caveats:
- One saved mid-chat is followed from the tool's result; from the next
  sign-in it's in the instructions.
- Off in the evals (memory=False): nothing read or saved, so runs
  repeat. Kept until "forget my preferences".
"""

import sqlite3
from functools import cache
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langgraph.store.base import BaseStore
from langgraph.store.sqlite import SqliteStore

from ams_assistant.config import MEMORY_FILE
from ams_assistant.hr_tools import HRContext

NAMESPACE = "preferences"
# Every choice that can be saved, and how the instructions say it.
SAID = {
    ("answer_length", "short"): "keep answers short",
    ("answer_length", "detailed"): "give detailed answers",
    ("language", "English"): "answer in English",
    ("language", "Hindi"): "answer in Hindi",
}
NO_STORE = {"error": "Preferences can't be saved in this session."}


@cache
def get_store() -> SqliteStore:
    """The store, opened once per process and shared by every agent.
    check_same_thread=False: the app answers on several threads (the
    store has its own lock); autocommit, as SqliteStore expects."""
    MEMORY_FILE.parent.mkdir(exist_ok=True)
    store = SqliteStore(sqlite3.connect(MEMORY_FILE, check_same_thread=False,
                                        isolation_level=None))
    store.setup()  # creates its tables the first time
    return store


def read_preferences(store: BaseStore, employee_id: str) -> str:
    """Their saved preferences as the instructions say them: 'keep
    answers short; answer in Hindi', or 'none'."""
    saved = {item.key: item.value["value"]
             for item in store.search((NAMESPACE, employee_id))}
    said = [SAID[(key, value)] for key, value in sorted(saved.items())
            if (key, value) in SAID]
    return "; ".join(said) or "none"


@tool(parse_docstring=True)
def remember_preference(
    runtime: ToolRuntime[HRContext],
    answer_length: Literal["short", "detailed"] | None = None,
    language: Literal["English", "Hindi"] | None = None,
) -> dict:
    """Save how the person you are helping wants answers, for this and
    future chats.

    Use it when they say how they want answers from now on, e.g.
    "always keep it short" or "answer in Hindi". Only these choices can
    be saved: if they ask you to remember anything else, say you can't.

    Args:
        runtime: Added by the agent, never by the model.
        answer_length: short or detailed.
        language: English or Hindi.
    """
    if runtime.store is None:
        return NO_STORE
    chosen = {"answer_length": answer_length, "language": language}
    namespace = (NAMESPACE, runtime.context.employee_id)
    for key, value in chosen.items():
        if value:
            runtime.store.put(namespace, key, {"value": value})
    return {"saved": any(chosen.values()),
            "preferences": read_preferences(runtime.store,
                                            runtime.context.employee_id),
            "note": "Follow them from now on, in this chat and later ones."}


@tool
def forget_preferences(runtime: ToolRuntime[HRContext]) -> dict:
    """Delete every saved preference of the person you are helping (how
    they want answers). Use it when they ask you to forget them."""
    if runtime.store is None:
        return NO_STORE
    namespace = (NAMESPACE, runtime.context.employee_id)
    for item in runtime.store.search(namespace):
        runtime.store.delete(namespace, item.key)
    return {"deleted": True,
            "note": "Nothing about how they want answers is saved now; "
                    "go back to the defaults."}
