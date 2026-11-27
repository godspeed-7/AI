"""Watching live answers: thumbs, background checks, retention.

In:  record(employee_id, question, answer, messages) after each answer
     (app.py); feedback(row_id, thumbs, comment) from the thumbs.
Out: data/quality.sqlite: each answer with its flags (what the online
     checks found) and the person's thumbs; review_queue.py reads it.

Strategy: online checks are code, cheap and run in the background, so
nobody waits: a budget stop, the output check, the reviewer sending a
draft back, the backup model, a tool error, a "not allowed", an
off-topic block. A flag isn't a verdict: it chooses what a person
looks at (with thumbs-down and a random sample: review_queue.py).
Kept QUALITY_KEEP_DAYS, then deleted (HR data).

Caveats: what was asked and answered is stored here (with names, as
shown): only the reviewers may open this file.
"""

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta

from langchain.messages import AIMessage, ToolMessage

from ams_agent.budget import stopped_by
from ams_agent.config import (
    BACKUP,
    QUALITY_DB_PATH,
    QUALITY_KEEP_DAYS,
    SQLITE_WAIT,
)
from ams_agent.output_check import is_check_reply
from ams_agent.permissions import NOT_ALLOWED
from ams_agent.resilience import answered_by
from ams_agent.review import is_review_note
from ams_agent.topic_guard import is_guard_reply


def connect() -> sqlite3.Connection:
    QUALITY_DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(QUALITY_DB_PATH, timeout=SQLITE_WAIT)
    con.execute("CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY"
                " KEY, at TEXT, employee_id TEXT, question TEXT, answer"
                " TEXT, flags TEXT, thumbs INTEGER, comment TEXT)")
    return con


def checks(messages: list) -> list[str]:
    """The online checks: what happened in one run, from its messages."""
    flags = []
    for m in messages:
        if reason := stopped_by(m):
            flags.append(f"budget:{reason}")
        if is_check_reply(m):
            flags.append("output_check")
        if is_review_note(m):
            flags.append("reviewer_sent_back")
        if is_guard_reply(m):
            flags.append("off_topic")
        if isinstance(m, AIMessage) and answered_by(m) == BACKUP.name:
            flags.append("backup_model")
        if isinstance(m, ToolMessage) and (
                m.status == "error" or "unavailable right now" in m.text):
            flags.append(f"tool_error:{m.name}")
        if isinstance(m, ToolMessage) and NOT_ALLOWED in m.text:
            flags.append("not_allowed")
    return sorted(set(flags))


def record(employee_id: str, question: str, answer: str,
           messages: list) -> int:
    """Save the answer now; its checks run in the background."""
    with closing(connect()) as con:
        row = con.execute(
            "INSERT INTO answers (at, employee_id, question, answer, flags)"
            " VALUES (?, ?, ?, ?, '[]')",
            (datetime.now().isoformat(timespec="seconds"), employee_id,
             question, answer)).lastrowid
        con.commit()

    def flag() -> None:
        with closing(connect()) as con:
            con.execute("UPDATE answers SET flags = ? WHERE id = ?",
                        (json.dumps(checks(messages)), row))
            con.commit()
    threading.Thread(target=flag, daemon=True).start()
    return row


def feedback(row: int, thumbs: int | None, comment: str = "") -> None:
    """The person's thumbs (1 up, 0 down) and optional comment."""
    with closing(connect()) as con:
        con.execute("UPDATE answers SET thumbs = ?, comment = ? WHERE id = ?",
                    (thumbs, comment, row))
        con.commit()


def delete_old(days: int = QUALITY_KEEP_DAYS) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with closing(connect()) as con:
        n = con.execute("DELETE FROM answers WHERE at < ?",
                        (cutoff,)).rowcount
        con.commit()
    return n
