"""What the person sees: names on screen, plain errors (walk 13).

In:  for_person(text): an answer (or a Confirm summary) as the model
     wrote it; error_message(error): a failed run's exception.
Out: the same text with each employee ID shown with its name; a plain
     message saying whether trying again can help.

Strategy: Gemini works with IDs only (it never needs names), so names
go back in at the very end, for the screen: "AMS-1019" -> "Sneha Pillai
(AMS-1019)". The chat history keeps the IDs, because it is resent to
the model with the next question. The app and the eval runner both use
for_person, so a test grades what the person sees. Errors: the person
gets what happened and what to do, never an exception's name; the
details go to the log.

Caveats: names the person types still reach Gemini (their own words;
replacing them is Presidio's job, left for later). An ID already next
to its name isn't doubled.
"""

import logging
import re

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
    unreachable = (ModelError, ConnectionError, TimeoutError,
                   httpx.TransportError)  # Gemini, or Ollama's backup
    if isinstance(error, unreachable) or "RESOURCE_EXHAUSTED" in str(error):
        return NO_MODEL
    return OUR_SIDE
