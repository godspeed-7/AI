"""The Gemini models: one place that makes them, one shared pace.

In:  chat_model(timeout) from agent.py (the agent) and topic_guard.py
     (the check).
Out: a ChatGoogleGenerativeAI client; every one shares PACE.

Strategy: client-side throttling. The free tier allows 15 calls a
minute per model, counted across the guard and the agent, so every
call waits its turn on one shared limiter (a token bucket) set below
that, instead of failing with 429 and being retried. The bucket holds
3, so a single question doesn't wait between its own calls.

Caveats: the limiter lives in this process: the app and an eval run at
the same time each have their own, and together can still go over.
"""

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

from ams_agent.config import AGENT_MODEL, AGENT_RETRIES, CALLS_PER_MINUTE

# A burst of 3 lets one question's calls (guard, model, model) go at
# once; in any minute: 3 + 12 refills = at most 15, the free tier's cap.
PACE = InMemoryRateLimiter(requests_per_second=CALLS_PER_MINUTE / 60,
                           max_bucket_size=3)


def chat_model(timeout: float, model: str = AGENT_MODEL):
    return ChatGoogleGenerativeAI(model=model, timeout=timeout,
                                  max_retries=AGENT_RETRIES,
                                  rate_limiter=PACE)
