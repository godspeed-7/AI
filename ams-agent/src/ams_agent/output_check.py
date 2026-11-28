"""The output check: an answer that leaks the system prompt is replaced.

In:  PromptLeakCheck(prompt), in the agent's middleware (agent.py).
Out: nothing (the answer stands), or the answer replaced by SAFE_REPLY.

How: code, no model call: the answer leaks if it holds the CANARY or
LEAK_WORDS words in a row from the prompt.

Watch out: catches quotes, not paraphrases: the prompt holds no secret.
"""

import logging
import re
import secrets

from langchain.agents.middleware import AgentMiddleware
from langchain.messages import AIMessage

from ams_agent.config import LEAK_WORDS

log = logging.getLogger(__name__)

CANARY = f"ams-{secrets.token_hex(4)}"  # new at each start, e.g. ams-3f9c1e7a
SAFE_REPLY = ("Sorry, I couldn't answer that. Please ask your manager or"
              " People Operations.")
CHECK_NAME = "output_check"  # marks the replacement among the messages


def words(text: str) -> list[str]:
    """Lower-case words, punctuation dropped: "Don't!" -> ["don", "t"]."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def shingles(text: str) -> set[tuple[str, ...]]:
    """Every run of LEAK_WORDS words in a row."""
    w = words(text)
    return {tuple(w[i:i + LEAK_WORDS])
            for i in range(len(w) - LEAK_WORDS + 1)}


def is_check_reply(message) -> bool:
    return isinstance(message, AIMessage) and message.name == CHECK_NAME


class PromptLeakCheck(AgentMiddleware):
    """Runs once per question, after the agent has answered."""

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt_shingles = shingles(prompt)

    def leaks(self, answer: str) -> bool:
        return (CANARY.lower() in answer.lower()
                or not shingles(answer).isdisjoint(self.prompt_shingles))

    def after_agent(self, state, runtime) -> dict | None:
        answer = state["messages"][-1]
        if not isinstance(answer, AIMessage) or not self.leaks(answer.text):
            return None
        log.warning("output check: the answer quoted the system prompt;"
                    " replaced")
        return {"messages": [AIMessage(SAFE_REPLY, id=answer.id,
                                       name=CHECK_NAME)]}
