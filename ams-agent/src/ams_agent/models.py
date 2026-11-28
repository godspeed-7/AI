"""Every model client, made from its job's settings in config.py.

In:  chat_model(job), e.g. chat_model(AGENT).
Out: a LangChain chat model with the job's limits; hide_keys(text).

How: the one file that knows the providers; jobs sharing a Pace share
one rate limiter, so a free tier's cap isn't hit.

Watch out: the limiter is per process (app + evals together can go over).
"""

import os
from functools import cache

from langchain_anthropic import ChatAnthropic
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

from ams_agent.config import JOBS, PROVIDER_KEYS, Model, Pace


def hide_keys(text: str) -> str:
    """The text with every provider's API key replaced by ***, so an
    error message can be logged."""
    for name in filter(None, PROVIDER_KEYS.values()):
        if key := os.environ.get(name):
            text = text.replace(key, "***")
    return text


@cache
def limiter(pace: Pace) -> InMemoryRateLimiter:
    """One limiter per Pace, shared by every job that uses it."""
    return InMemoryRateLimiter(requests_per_second=pace.per_minute / 60,
                               max_bucket_size=pace.burst)


def chat_model(job: Model, client_retries: bool = True,
               name: str | None = None):
    """client_retries=False: the client itself never retries (the
    agent's retries are middleware, resilience.py: one retry layer).
    name: what its calls are called in a trace; by default the job's
    name in JOBS ("guard", "reviewer"...)."""
    retries = job.retries if client_retries else 0
    name = name or next((j for j, (m, _) in JOBS.items() if m is job), None)
    pace = limiter(job.pace) if job.pace else None
    if job.provider == "anthropic":
        thinking = {"type": job.thinking} if job.thinking else None
        return ChatAnthropic(
            model=job.name, timeout=job.timeout, max_retries=retries,
            thinking=thinking, temperature=job.temperature,
            max_tokens=job.max_output, rate_limiter=pace, name=name)
    if job.provider == "google":
        return ChatGoogleGenerativeAI(
            model=job.name, timeout=job.timeout, max_retries=retries,
            thinking_level=job.thinking, temperature=job.temperature,
            max_output_tokens=job.max_output, rate_limiter=pace,
            name=name)
    if job.provider == "ollama":  # its client has no retries
        return ChatOllama(model=job.name, reasoning=job.thinking,
                          temperature=job.temperature,
                          client_kwargs={"timeout": job.timeout}, name=name)
    raise ValueError(f"unknown provider: {job.provider}")
