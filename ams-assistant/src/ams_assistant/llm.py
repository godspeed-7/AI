"""Chat models: build the LLM for a provider, with the reply cache.

In:  a provider ("ollama", "google" or "nvidia"), a model name and a
     temperature.
Out: build_llm(...) -> a LangChain chat model, ready for prompt | llm.

Strategy: "ollama" runs on this Mac (ChatOllama). Google AI Studio and
NVIDIA speak the OpenAI API, so ChatOpenAI reaches them with their
address and API key. chain.py (answers) and judge.py (grades) both
call build_llm, so either can run on any provider. The agent's Google
models use Google's own client instead (with_tools). Every model gets
the reply cache (llm_cache.py).

Caveats:
- A hosted provider needs the internet and its API key in the
  environment (GOOGLE_API_KEY, NVIDIA_API_KEY in ~/.zshrc); free-tier
  limits can change.
- Google's free tier limits tokens per minute for each model, so its
  calls are paced: one pacer per model, shared by every thread and
  chain (the answerer and the judge each have their own model).
- ChatOpenAI's cache key includes its settings (e.g. the address), so
  changing one re-runs every hosted call once; the time limit and
  retries are left out of it (llm_cache.py).
"""

import os
from functools import cache

from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from ams_assistant.config import (
    BATCH_RETRIES,
    BATCH_TIMEOUT,
    GOOGLE_BASE_URL,
    GOOGLE_CALLS_PER_MINUTE,
    LOCAL_TIMEOUT,
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
              reasoning: bool | None = None,
              with_tools: bool = False,
              timeout: float = BATCH_TIMEOUT,
              retries: int = BATCH_RETRIES) -> BaseChatModel:
    """Return the chat model `model` on `provider`, with its cache.

    reasoning (Ollama thinking models such as qwen3 only): True returns
    the thinking apart from the reply, in
    additional_kwargs["reasoning_content"]; False switches thinking
    off; None leaves the model's default.
    with_tools (Google only): the model will call tools (the agent), so
    use Google's own client; see below.
    timeout, retries (hosted models): seconds before a call gives up,
    and how many times it's tried again; batch values unless given
    (the agent passes its shorter ones, config.py). Ollama always gets
    LOCAL_TIMEOUT and no retries.
    """
    # ChatOllama's cache key ignores `reasoning`, but replies with and
    # without thinking differ, so it goes into the model label.
    label = model if reasoning is None else f"{model} reasoning={reasoning}"
    llm_cache = get_llm_cache(label, temperature)
    if provider == "ollama":
        # client_kwargs go to Ollama's HTTP client; not in the cache key.
        return ChatOllama(model=model, temperature=temperature,
                          reasoning=reasoning, cache=llm_cache,
                          client_kwargs={"timeout": LOCAL_TIMEOUT})

    base_url, key_name, per_minute = HOSTED[provider]
    pacer = get_pacer(model, per_minute) if per_minute else None
    if provider == "google" and with_tools:
        # Gemini 3 attaches a "thought signature" to each tool request
        # and rejects the next call (400) unless it comes back with the
        # tool's result. ChatOpenAI drops it; Google's client keeps it.
        # Its replies' content is a list of parts: read reply.text.
        return ChatGoogleGenerativeAI(
            model=model, temperature=temperature, cache=llm_cache,
            google_api_key=os.environ[key_name], rate_limiter=pacer,
            timeout=timeout, max_retries=retries)
    # max_retries waits and retries on "too many requests" (429) and
    # on the free tiers' brief "overloaded" errors (500/503).
    return ChatOpenAI(model=model, temperature=temperature,
                      cache=llm_cache, base_url=base_url,
                      api_key=os.environ[key_name], rate_limiter=pacer,
                      timeout=timeout, max_retries=retries)
