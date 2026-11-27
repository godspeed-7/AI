"""Every model client, made from its job's settings in config.py.

In:  chat_model(job), with a job from config.py (AGENT, GUARD, ...).
Out: a LangChain chat model (ChatGoogleGenerativeAI or ChatOllama) with
     the job's time limit, retries, thinking, temperature and pace.

Strategy: the one place that knows the providers, so the other files
ask for a job, never a provider, and moving a job to another model is a
config change. Client-side throttling: jobs with the same Pace share
one limiter (a token bucket), so together they stay under a free
tier's per-minute cap instead of failing with 429 and being retried.

Caveats: a limiter lives in this process: the app and an eval run at
the same time each have their own, and together can still go over.
"""

from functools import cache

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from ams_agent.config import Model, Pace


@cache
def limiter(pace: Pace) -> InMemoryRateLimiter:
    """One limiter per Pace, shared by every job that uses it."""
    return InMemoryRateLimiter(requests_per_second=pace.per_minute / 60,
                               max_bucket_size=pace.burst)


def chat_model(job: Model, client_retries: bool = True):
    """client_retries=False: the client itself never retries (the
    agent's retries are middleware, resilience.py: one retry layer)."""
    retries = job.retries if client_retries else 0
    if job.provider == "google":
        return ChatGoogleGenerativeAI(
            model=job.name, timeout=job.timeout, max_retries=retries,
            thinking_level=job.thinking, temperature=job.temperature,
            rate_limiter=limiter(job.pace) if job.pace else None)
    if job.provider == "ollama":  # its client has no retries
        return ChatOllama(model=job.name, reasoning=job.thinking,
                          temperature=job.temperature,
                          client_kwargs={"timeout": job.timeout})
    raise ValueError(f"unknown provider: {job.provider}")
