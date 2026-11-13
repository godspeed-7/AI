"""Prompt versions: a prompt kept in Langfuse, numbered, with labels
(EVAL_PLAYBOOK.md, stage A). For now, the agent's instructions.

In:  a prompt's name and the code's copy of its text (Langfuse's
     {{placeholder}} syntax); PROMPT_LABEL (config.py).
Out: get_prompt(name, fallback) -> the version with PROMPT_LABEL:
     .compile(...) fills it in, .version says which (0: the code's).
     link_prompt(prompt) -> middleware that names that version on the
     agent's model calls in a trace.

Strategy: a prompt changes in Langfuse, not in the code: a new
version, tried as "staging", goes live when the "production" label
moves to it, and back the same way. The SDK keeps a prompt for 60 s,
so a move shows in agents built after that (the app: at sign-in). In
a trace each model call names its version (propagate_attributes), so
Langfuse shows scores, cost and time per version.

Caveats:
- Langfuse unreachable, no keys, or no such prompt: the code's copy
  runs, with a warning, and isn't named. Keep it close to production:
  copy a version that wins into the code.
- Only the agent's own model calls are named; the Reflection checker
  (middleware.py) has its own prompt, kept in code.
"""

import logging
from collections.abc import Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    wrap_model_call,
)
from langfuse import propagate_attributes
from langfuse.api import Prompt_Text
from langfuse.api.core import ApiError
from langfuse.model import TextPromptClient

from ams_assistant.config import PROMPT_LABEL
from ams_assistant.tracing import langfuse_client

logger = logging.getLogger(__name__)


def get_prompt(name: str, fallback: str) -> TextPromptClient:
    """The version of prompt `name` with PROMPT_LABEL, from Langfuse;
    `fallback` (version 0) if Langfuse can't give it."""
    try:
        # A failed fetch returns the fallback, with the SDK's warning.
        return langfuse_client().get_prompt(name, label=PROMPT_LABEL,
                                            fallback=fallback)
    except ApiError:  # no keys: the SDK refuses before it asks
        logger.warning("Langfuse has no keys (LANGFUSE_* in ~/.zshrc): "
                       "%s runs from the code's copy", name)
        return TextPromptClient(
            Prompt_Text(name=name, prompt=fallback, version=0, config={},
                        labels=[], tags=[]),
            is_fallback=True,
        )


def link_prompt(prompt: TextPromptClient) -> AgentMiddleware:
    """Middleware: in a traced run, each of the agent's model calls
    names `prompt`'s version (the code's copy is never named)."""
    @wrap_model_call
    def name_prompt_version(
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        if prompt.is_fallback:
            return handler(request)
        # Generations started inside carry the prompt's name + version.
        with propagate_attributes(prompt=prompt):
            return handler(request)

    return name_prompt_version
