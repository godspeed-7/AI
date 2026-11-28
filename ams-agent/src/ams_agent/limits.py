"""Request limits, checked in code before the agent runs.

In:  too_long(text), RateLimiter.wait(employee_id), from app.py.
Out: too_long -> the reason to show, or None; wait -> 0, or the
     seconds until the next question may go.

How: MAX_MESSAGE_CHARS per message; MAX_QUESTIONS_PER_MINUTE per
person (a sliding window).

Watch out: kept in memory: a restart resets them.
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
