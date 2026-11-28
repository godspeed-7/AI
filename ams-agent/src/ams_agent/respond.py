"""What the person sees: names next to IDs, plain error messages.

In:  for_person(text), error_message(error).
Out: the text with each ID shown with its name ("Sneha Pillai
     (AMS-1019)"); a plain message saying whether retrying helps.

How: the model works with IDs only; names go back in at the very end,
for the screen. The chat history keeps the IDs.

Watch out: names the person types still reach the model.
"""

import logging
import re

import anthropic
import httpx
from langchain_core.exceptions import ModelError

from ams_agent.db import find_employee

log = logging.getLogger(__name__)
EMPLOYEE_ID = re.compile(r"\bAMS-\d{4}\b")

NO_MODEL = ("I can't reach the AI model right now. Please try again in a"
            " few minutes.")
OUR_SIDE = ("Something went wrong on our side. Please try again; if it"
            " keeps happening, contact People Operations.")


def for_person(text: str) -> str:
    """Each employee ID with its name, unless the name is already there."""
    def named(match: re.Match) -> str:
        person = find_employee(match.group(0))
        if not person:
            return match.group(0)
        before = text[max(0, match.start() - 40):match.start()]
        if person["name"].split()[0] in before:
            return match.group(0)  # "Ananya (AMS-1015)": already named
        if text[match.start() - 1:match.start()] == "(":
            return f"{person['name']}, {match.group(0)}"  # "(Name, ID)"
        return f"{person['name']} ({match.group(0)})"
    return EMPLOYEE_ID.sub(named, text)


def error_message(error: BaseException) -> str:
    """A plain message for a failed run; the details go to the log."""
    log.error("the agent failed: %s: %s", type(error).__name__, error)
    # Can't reach it, or it's busy: Gemini's errors (ModelError), Claude's
    # (a dropped connection; 408, 429, 5xx), the network. A bad key or
    # an empty credit balance (400-403) is our side.
    unreachable = (ModelError, ConnectionError, TimeoutError,
                   httpx.TransportError, anthropic.APIConnectionError)
    status = getattr(error, "status_code", None)
    busy = isinstance(status, int) and (status in (408, 429)
                                        or status >= 500)
    if (isinstance(error, unreachable) or busy
            or "RESOURCE_EXHAUSTED" in str(error)):
        return NO_MODEL
    return OUR_SIDE
