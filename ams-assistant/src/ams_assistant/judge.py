"""LLM judge: grade one generated answer.

In:  {"question", "expected_answer", "retrieved_context",
     "generated_answer"}.
Out: build_judge().invoke(...) -> a Scores object: correctness,
     context_support and completeness (each 0, 1 or 2), explanation.

Strategy: the instructions come from ams-data/judge_prompt.txt (copied
word for word from basic-rag's judge.py), so both projects are graded
the same way. with_structured_output(Scores) makes the model reply in
the shape of Scores and checks it, replacing basic-rag's hand-written
JSON parsing and score validation. The model is built by llm.py.

Caveats:
- "google" (Gemma 4 26B, the default): ~3 s per grade, but paced to
  GOOGLE_CALLS_PER_MINUTE to stay under the free tier's tokens per
  minute, so a full run takes ~45 minutes. On a 40-answer key it
  agreed 28/35; it rarely gives partial marks and once passed a
  confident "the policy doesn't cover it" that was wrong.
- "nvidia" (Nemotron 3 Ultra) was the strictest (35/40), but its free
  quota runs out after ~200 grades and returns hours later.
- Only compare scores graded by the same judge.
- At temperature 0 Gemma sometimes gets stuck repeating itself (D5,
  2026-11-14: "ful" for 11 minutes), and on every run, as the same
  prompt gets the same reply. Replies stop at JUDGE_MAX_TOKENS, and a
  broken one is asked for once more at JUDGE_RETRY_TEMPERATURE,
  uncached: those few grades can differ between runs.
- Raises an error if the retry doesn't fit Scores either (e.g. a score
  of 3); the evals then count the question as failed.
"""

from typing import Literal

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from openai import LengthFinishReasonError
from pydantic import BaseModel, ValidationError

from ams_assistant.config import (
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL,
    JUDGE_PROMPT_FILE,
    JUDGE_PROVIDER,
    JUDGE_RETRY_TEMPERATURE,
)
from ams_assistant.llm import build_llm

JUDGE_PROMPT = ChatPromptTemplate.from_template(
    JUDGE_PROMPT_FILE.read_text(encoding="utf-8")
)


class Scores(BaseModel):
    """The judge's verdict. Pydantic checks the types (like a zod
    schema in JS): Literal[0, 1, 2] rejects anything else."""

    correctness: Literal[0, 1, 2]
    context_support: Literal[0, 1, 2]
    completeness: Literal[0, 1, 2]
    explanation: str

    @property
    def total(self) -> int:
        """Sum of the three scores, 0-6."""
        return self.correctness + self.context_support + self.completeness


# A reply that isn't a Scores: cut off at JUDGE_MAX_TOKENS (Google),
# not valid JSON or a score outside 0-2 (Google), or either one from
# Ollama.
BROKEN_REPLY = (LengthFinishReasonError, ValidationError,
                OutputParserException)


def grader(temperature: float, cached: bool = True):
    """The judge's model at `temperature`, replying with a Scores."""
    llm = build_llm(JUDGE_PROVIDER, JUDGE_MODEL, temperature,
                    max_tokens=JUDGE_MAX_TOKENS, cached=cached)
    # with_structured_output sends Scores' JSON schema to the model,
    # which constrains the reply to it, then turns the JSON into a
    # Scores.
    return llm.with_structured_output(Scores, method="json_schema")


def build_judge():
    """Return the chain: judge inputs -> Scores."""
    # temperature 0 keeps grading repeatable, so a saved grade
    # (llm_cache.py) is reused when the same answer comes back. A
    # broken reply is asked for once more (see Caveats); any other
    # error (e.g. Google's 500s) has the client's own retries.
    retry = grader(JUDGE_RETRY_TEMPERATURE, cached=False)
    return JUDGE_PROMPT | grader(0).with_fallbacks(
        [retry], exceptions_to_handle=BROKEN_REPLY)
