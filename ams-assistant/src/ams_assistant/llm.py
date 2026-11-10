"""Chat models: build the LLM for a provider, with the reply cache.

In:  a provider ("ollama", "google" or "nvidia"), a model name and a
     temperature.
Out: build_llm(...) -> a LangChain chat model, ready for prompt | llm.

Strategy: "ollama" runs on this Mac (ChatOllama). Google AI Studio and
NVIDIA speak the OpenAI API, so ChatOpenAI reaches them with their
address and API key. chain.py (answers) and judge.py (grades) both
call build_llm, so either can run on any provider. Every model gets
the reply cache (llm_cache.py).

Caveats:
- A hosted provider needs the internet and its API key in the
  environment (GOOGLE_API_KEY, NVIDIA_API_KEY in ~/.zshrc); free-tier
  limits can change.
- Google's free tier limits tokens per minute for each model, so its
  calls are paced: one pacer per model, shared by every thread and
  chain (the answerer and the judge each have their own model).
- ChatOpenAI's cache key includes its settings (timeout, retries,
  address), so changing one re-runs every hosted call once.
"""

import os
from functools import cache

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from ams_assistant.config import (
    GOOGLE_BASE_URL,
    GOOGLE_CALLS_PER_MINUTE,
    NVIDIA_BASE_URL,
)
from ams_assistant.llm_cache import get_llm_cache

# Hosted providers: their address, the environment variable that holds
# the key, and the most calls a minute per model (None = no pacing).
HOSTED = {
    "google": (GOOGLE_BASE_URL, "GOOGLE_API_KEY", GOOGLE_CALLS_PER_MINUTE),
    "nvidia": (NVIDIA_BASE_URL, "NVIDIA_API_KEY", None),
}


# @cache: the same model always gets the same pacer.
@cache
def get_pacer(model: str, per_minute: int) -> InMemoryRateLimiter:
    """Space out one model's real calls (cached replies skip it);
    max_bucket_size=1 allows no bursts."""
    return InMemoryRateLimiter(requests_per_second=per_minute / 60,
                               max_bucket_size=1)


def build_llm(provider: str, model: str, temperature: float,
              reasoning: bool | None = None) -> BaseChatModel:
    """Return the chat model `model` on `provider`, with its cache.

    reasoning (Ollama thinking models such as qwen3 only): True returns
    the thinking apart from the reply, in
    additional_kwargs["reasoning_content"]; False switches thinking
    off; None leaves the model's default.
    """
    # ChatOllama's cache key ignores `reasoning`, but replies with and
    # without thinking differ, so it goes into the model label.
    label = model if reasoning is None else f"{model} reasoning={reasoning}"
    llm_cache = get_llm_cache(label, temperature)
    if provider == "ollama":
        return ChatOllama(model=model, temperature=temperature,
                          reasoning=reasoning, cache=llm_cache)

    base_url, key_name, per_minute = HOSTED[provider]
    pacer = get_pacer(model, per_minute) if per_minute else None
    # max_retries waits and retries on "too many requests" (429) and
    # on the free tiers' brief "overloaded" errors (500/503).
    return ChatOpenAI(model=model, temperature=temperature,
                      cache=llm_cache, base_url=base_url,
                      api_key=os.environ[key_name], rate_limiter=pacer,
                      timeout=300, max_retries=4)
