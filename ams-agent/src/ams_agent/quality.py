"""Watching live answers: thumbs, background checks, retention.

In:  record(...) after each answer; feedback(...) from the thumbs.
Out: data/quality.sqlite (each answer, its flags, its thumbs) and the
     same as scores on the answer's Langfuse trace.

How: cheap code checks run in the background (ONLINE_CHECKS); a flag
picks what a person reviews (review_queue.py), it isn't a verdict.

Watch out: holds real questions and answers: reviewers only.
"""

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timedelta

from langchain.messages import AIMessage, ToolMessage

from ams_agent import tracing
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

# Each online check's name, as a flag's first part ("budget:tokens").
ONLINE_CHECKS = ("budget", "output_check", "reviewer_sent_back",
                 "off_topic", "backup_model", "tool_error", "not_allowed")


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


def score_checks(trace_id: str | None, flags: list[str]) -> None:
    """Each online check as a score on the answer's trace: 1 = it fired
    (the comment says how: "budget:tokens"), 0 = it didn't."""
    for check in ONLINE_CHECKS:
        fired = [f for f in flags if f.split(":")[0] == check]
        tracing.score(trace_id, check, int(bool(fired)), ", ".join(fired))


def record(employee_id: str, question: str, answer: str,
           messages: list, trace_id: str | None = None) -> int:
    """Save the answer now; its checks run in the background."""
    with closing(connect()) as con:
        row = con.execute(
            "INSERT INTO answers (at, employee_id, question, answer, flags)"
            " VALUES (?, ?, ?, ?, '[]')",
            (datetime.now().isoformat(timespec="seconds"), employee_id,
             question, answer)).lastrowid
        con.commit()

    def flag() -> None:
        flags = checks(messages)
        with closing(connect()) as con:
            con.execute("UPDATE answers SET flags = ? WHERE id = ?",
                        (json.dumps(flags), row))
            con.commit()
        score_checks(trace_id, flags)
    threading.Thread(target=flag, daemon=True).start()
    return row


def feedback(row: int, thumbs: int | None, comment: str = "",
             trace_id: str | None = None) -> None:
    """The person's thumbs (1 up, 0 down) and optional comment; on the
    trace too, one per answer (a change replaces it, un-clicked deletes
    it)."""
    with closing(connect()) as con:
        con.execute("UPDATE answers SET thumbs = ?, comment = ? WHERE id = ?",
                    (thumbs, comment, row))
        con.commit()
    if not trace_id:
        return
    score_id = f"{trace_id}-thumbs"
    if thumbs is None:
        tracing.unscore(score_id)
    else:
        tracing.score(trace_id, "thumbs", thumbs, comment, score_id)


def delete_old(days: int = QUALITY_KEEP_DAYS) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with closing(connect()) as con:
        n = con.execute("DELETE FROM answers WHERE at < ?",
                        (cutoff,)).rowcount
        con.commit()
    return n
