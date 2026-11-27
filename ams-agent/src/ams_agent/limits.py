"""Request limits, checked in code before the agent runs.

In:  too_long(text) and RateLimiter.wait(employee_id), called by app.py
     before each question.
Out: too_long -> the reason to show, or None; wait -> 0 if the question
     may go on (and counts it), else the seconds until it may.

Strategy: deterministic, so they never let a request through by
chance, and they cost no model call. A message over MAX_MESSAGE_CHARS
is refused. Each employee gets MAX_QUESTIONS_PER_MINUTE in any 60
seconds (a sliding window). The counts live in the server process,
shared by every browser tab, so a refresh doesn't reset them.

Caveats: kept in memory, so a restart resets them and two servers
wouldn't share them; production keeps them in a shared store (e.g.
Redis) or the API gateway. The eval runner doesn't use them: it tests
the agent, not the app.
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from ams_agent.config import MAX_MESSAGE_CHARS


def too_long(text: str) -> str | None:
    """Why a message is refused for its length, or None if it's fine."""
    if len(text) > MAX_MESSAGE_CHARS:
        return (f"That message is {len(text):,} characters; please keep it"
                f" under {MAX_MESSAGE_CHARS:,}.")
    return None


class RateLimiter:
    """At most `limit` questions per person in any `window` seconds."""

    def __init__(self, limit: int, window: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock  # a fake clock in tests
        self._asked: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()  # one server, many browser tabs

    def wait(self, person: str) -> float:
        """0 if `person` may ask now (counted), else seconds to wait."""
        now = self.clock()
        with self._lock:
            asked = self._asked[person]
            while asked and now - asked[0] >= self.window:
                asked.popleft()  # older than the window: no longer counts
            if len(asked) >= self.limit:
                return self.window - (now - asked[0])
            asked.append(now)
            return 0.0
