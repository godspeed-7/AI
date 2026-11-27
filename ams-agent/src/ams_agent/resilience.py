"""When a model call fails: retry what can pass, then the backup.

In:  recovery(fallback), the agent's model-call middleware (agent.py);
     the models: config.AGENT and config.BACKUP (also the guard's).
Out: a model answer from Gemini, or from local qwen3:8b when Gemini
     keeps failing; answered_by(message) says which.

Strategy, from the outside in:
- CircuitBreaker: after BREAKER_FAILURES Gemini failures in a row, skip
  Gemini for BREAKER_SECONDS and go straight to the backup (no waiting
  for an error we know is coming), then try Gemini once again.
- ModelFallbackMiddleware (LangChain): a call that still fails goes to
  the backup (thinking on, as always for qwen3).
- ModelRetryMiddleware (LangChain): retry only what can pass (a
  time-out, 429 per minute, 5xx), waiting longer each time; never a
  bad key or request (is_retryable False), nor the daily quota ("retry
  in 14 hours" won't pass in seconds). The one retry layer: the Gemini
  client itself doesn't retry the agent's calls.
The evals use none of the backup (fallback=False): they measure Gemini.

Caveats: the breaker lives in this process (one per server). The
backup needs Ollama running locally; it is slower (~13 s a round).
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
    """Retry only what can pass: LangChain's rule, minus the daily quota."""
    return DAILY_QUOTA not in str(error) and default_retry_on(error)


def answered_by(message) -> str:
    """The model that wrote a message, from its metadata."""
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("model_name") or meta.get("model") or ""


class Breaker:
    """Counts Gemini failures in a row; open = skip Gemini for a while."""

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
                self.opened = None  # half-open: Gemini gets one more try
                self.in_a_row = self.failures - 1
                return False
            return True

    def record(self, gemini_ok: bool) -> None:
        with self.lock:
            if gemini_ok:
                self.in_a_row, self.opened = 0, None
                return
            self.in_a_row += 1
            if self.in_a_row >= self.failures and self.opened is None:
                self.opened = self.clock()
                log.warning("Gemini failed %d times in a row: backup only"
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
            self.breaker.record(gemini_ok=False)
            raise
        last = response.result[-1] if response.result else None
        self.breaker.record(gemini_ok=answered_by(last) != BACKUP.name)
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
