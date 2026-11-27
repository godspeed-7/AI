"""When a model call fails: retry what can pass, then the backup.

In:  recovery(fallback), the agent's model-call middleware (agent.py);
     the models: config.AGENT and config.BACKUP (also the guard's).
Out: a model answer from the main model (AGENT), or from the backup
     (another company's) when it keeps failing; answered_by(message)
     says which.

Strategy, from the outside in:
- CircuitBreaker: after BREAKER_FAILURES main-model failures in a row,
  skip it for BREAKER_SECONDS and go straight to the backup (no waiting
  for an error we know is coming), then try the main model once again.
- ModelFallbackMiddleware (LangChain): a call that still fails goes to
  the backup.
- ModelRetryMiddleware (LangChain): retry only what can pass (a
  time-out, a dropped connection, 429 too many requests, 5xx), waiting
  longer each time; never a bad key or request (400, 401, 403), an
  empty credit balance, nor Gemini's daily quota ("retry in 14 hours"
  won't pass in seconds). The one retry layer: the agent's client
  itself doesn't retry.
The evals use none of the backup (fallback=False): they measure the
main model.

Caveats: the breaker lives in this process (one per server).
"""

import logging
import threading
import time

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
)
from langchain.agents.middleware._retry import default_retry_on

from ams_agent.config import AGENT, BACKUP, BREAKER_FAILURES, BREAKER_SECONDS
from ams_agent.models import chat_model

log = logging.getLogger(__name__)
DAILY_QUOTA = "PerDay"  # in Google's error once the day's requests are used


def can_retry(error: BaseException) -> bool:
    """Retry only what can pass. Claude's errors carry an HTTP status
    (LangChain doesn't sort them); others follow LangChain's rule,
    minus Gemini's daily quota."""
    if DAILY_QUOTA in str(error):
        return False
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status in (408, 409, 429) or status >= 500
    return default_retry_on(error)


def answered_by(message) -> str:
    """The model that wrote a message, from its metadata."""
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("model_name") or meta.get("model") or ""


class Breaker:
    """Counts main-model failures in a row; open = skip it for a while."""

    def __init__(self, failures: int = BREAKER_FAILURES,
                 seconds: float = BREAKER_SECONDS, clock=time.monotonic):
        self.failures, self.seconds, self.clock = failures, seconds, clock
        self.in_a_row, self.opened = 0, None
        self.lock = threading.Lock()

    def is_open(self) -> bool:
        with self.lock:
            if self.opened is None:
                return False
            if self.clock() - self.opened >= self.seconds:
                self.opened = None  # half-open: one more try
                self.in_a_row = self.failures - 1
                return False
            return True

    def record(self, main_ok: bool) -> None:
        with self.lock:
            if main_ok:
                self.in_a_row, self.opened = 0, None
                return
            self.in_a_row += 1
            if self.in_a_row >= self.failures and self.opened is None:
                self.opened = self.clock()
                log.warning("Main model failed %d times in a row: backup only"
                            " for %d s", self.in_a_row, self.seconds)


class CircuitBreaker(AgentMiddleware):
    """Outermost: while open, every call goes to the backup directly."""

    def __init__(self, backup, breaker: Breaker) -> None:
        super().__init__()
        self.backup, self.breaker = backup, breaker

    def wrap_model_call(self, request, handler):
        if self.breaker.is_open():
            return handler(request.override(model=self.backup))
        try:
            response = handler(request)
        except Exception:
            self.breaker.record(main_ok=False)
            raise
        last = response.result[-1] if response.result else None
        self.breaker.record(main_ok=answered_by(last) != BACKUP.name)
        return response


BREAKER = Breaker()  # one per process: every chat shares what it learns


def recovery(fallback: bool = True) -> list[AgentMiddleware]:
    """The model-call middleware, outermost first; retries only with
    fallback=False (the evals)."""
    retry = ModelRetryMiddleware(max_retries=AGENT.retries,
                                 retry_on=can_retry, on_failure="error")
    if not fallback:
        return [retry]
    backup = chat_model(BACKUP)
    return [CircuitBreaker(backup, BREAKER), ModelFallbackMiddleware(backup),
            retry]
