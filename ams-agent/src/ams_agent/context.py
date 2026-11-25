"""Who is asking: the trusted context every tool reads.

Set by the app at sign-in (app.py) or by the eval runner for each
question, never by the model or the chat, so a question can't switch
person ("I am Pooja") and read someone else's records (stops
IDOR/BOLA).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    employee_id: str  # e.g. "AMS-1015"
