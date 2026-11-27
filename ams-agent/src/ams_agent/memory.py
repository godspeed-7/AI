"""What the app keeps after an answer, and for how long.

In:  open_memory() once per app; chat_id(employee_id) from sign-in.
Out: a durable checkpointer (each person's chat, and a pending Confirm)
     (data/chats.sqlite) and store (their preferences,
     data/preferences.sqlite); the
     preference tools; history() and pending() to redraw a chat after a
     refresh or restart; delete_old_chats() for retention.

Strategy: three storages, three jobs. The checkpointer holds one chat:
its messages and a paused booking, so a refresh, a restart or a crash
loses nothing. The chat ID comes from sign-in (one ongoing chat per
person), never from the user, so nobody can open someone else's chat
(no IDOR on chats); "New chat" deletes it and starts fresh. The store
holds facts across chats, but only from ALLOWED (how to answer: short
or detailed), never secrets, guesses or anyone else's data; the person
can see them (they're in the prompt) and forget them. Retention: a chat
unused for CHAT_KEEP_DAYS is deleted, at app start and at sign-in.
Long chats are summarised in the agent (SummarizationMiddleware).

Caveats: two tabs as the same person share one chat. The live step
traces aren't kept, only the questions and answers. The evals keep
everything in memory instead (agent.py's defaults).
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Literal

from langchain.messages import AIMessage, HumanMessage
from langchain.tools import ToolRuntime, tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

from ams_agent.config import CHAT_KEEP_DAYS, CHATS_DB_PATH, PREFERENCES_DB_PATH
from ams_agent.context import Context

# The only preferences kept across chats, and their allowed values.
ALLOWED = {"answer_style": ("short", "detailed")}


def chat_id(employee_id: str) -> str:
    """The person's chat: from sign-in, never from the chat or the URL."""
    return f"chat-{employee_id}"


def open_memory() -> tuple[SqliteSaver, SqliteStore]:
    """The durable checkpointer and store, and our own chats table."""
    CHATS_DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(CHATS_DB_PATH, check_same_thread=False)
    saver = SqliteSaver(con)
    saver.setup()
    # Its own file: two connections writing one file would lock it.
    # isolation_level=None: the store runs its own transactions.
    store = SqliteStore(sqlite3.connect(PREFERENCES_DB_PATH,
                                        check_same_thread=False,
                                        isolation_level=None))
    store.setup()
    con.execute("CREATE TABLE IF NOT EXISTS chats"
                " (employee_id TEXT PRIMARY KEY, last_used TEXT)")
    con.commit()
    return saver, store


def touch(saver: SqliteSaver, employee_id: str) -> None:
    """The person used their chat now (for retention)."""
    saver.conn.execute(
        "INSERT INTO chats VALUES (?, ?) ON CONFLICT(employee_id)"
        " DO UPDATE SET last_used = excluded.last_used",
        (employee_id, datetime.now().isoformat(timespec="seconds")))
    saver.conn.commit()


def delete_old_chats(saver: SqliteSaver, days: int = CHAT_KEEP_DAYS,
                     now: datetime | None = None) -> list[str]:
    """Delete every chat unused for `days`; returns whose."""
    cutoff = ((now or datetime.now()) - timedelta(days=days)).isoformat()
    old = [r[0] for r in saver.conn.execute(
        "SELECT employee_id FROM chats WHERE last_used < ?", (cutoff,))]
    for employee_id in old:
        saver.delete_thread(chat_id(employee_id))
        saver.conn.execute("DELETE FROM chats WHERE employee_id = ?",
                           (employee_id,))
    saver.conn.commit()
    return old


def new_chat(saver: SqliteSaver, employee_id: str) -> None:
    """Forget the person's chat (the "New chat" button)."""
    saver.delete_thread(chat_id(employee_id))


def history(agent, employee_id: str) -> list[dict]:
    """The saved chat as questions and answers (steps aren't kept)."""
    state = agent.get_state({"configurable":
                             {"thread_id": chat_id(employee_id)}})
    turns = []
    for m in state.values.get("messages", []) if state else []:
        if isinstance(m, HumanMessage) and not m.name and \
                not m.additional_kwargs.get("lc_source"):
            turns.append({"question": m.text, "steps": [], "answer": ""})
        elif isinstance(m, AIMessage) and m.text.strip() and turns:
            turns[-1]["answer"] = m.text  # the last answer in the turn
    return turns


def pending(agent, employee_id: str):
    """A booking still waiting for Confirm in this chat, or None."""
    state = agent.get_state({"configurable":
                             {"thread_id": chat_id(employee_id)}})
    interrupts = getattr(state, "interrupts", ()) if state else ()
    return interrupts[0].value if interrupts else None


def preferences(store, employee_id: str) -> dict:
    """What the person asked the assistant to remember."""
    if store is None:
        return {}
    return {item.key: item.value["value"]
            for item in store.search(("preferences", employee_id))}


@tool(parse_docstring=True)
def remember_preference(runtime: ToolRuntime[Context],
                        name: Literal["answer_style"],
                        value: Literal["short", "detailed"]) -> str:
    """Remember how the signed-in employee wants to be answered, for
    their later chats too. Only when they ask for it.

    Args:
        name: Which preference: answer_style.
        value: For answer_style: short or detailed.
    """
    if value not in ALLOWED.get(name, ()):
        return f"Can't remember that: only {ALLOWED} are kept."
    runtime.store.put(("preferences", runtime.context.employee_id), name,
                      {"value": value})
    return (f"Remembered: {name} = {value}. Say 'forget my preferences'"
            " to remove it.")


@tool
def forget_preferences(runtime: ToolRuntime[Context]) -> str:
    """Forget everything remembered about how the signed-in employee wants
    to be answered."""
    namespace = ("preferences", runtime.context.employee_id)
    for item in runtime.store.search(namespace):
        runtime.store.delete(namespace, item.key)
    return "Forgotten: no preferences are kept now."
