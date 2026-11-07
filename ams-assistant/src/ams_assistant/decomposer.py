"""Query decomposition: split a question that asks several things into
one search query per thing.

In:  {"question": "Where is the mailroom in Pune, and when is it
     open?"}
Out: build_decomposer().invoke(...) -> the sub-questions, e.g.
     ["Where is the mailroom at the Pune office?", "What are the
     mailroom opening hours at the Pune office?"]; a question that
     asks one thing comes back unchanged, as a list of one.

Strategy: one search for a two-part question tends to return chunks
for only one part (26 hits found only half of their sections). Each
sub-question is searched and reranked on its own and the results are
merged by taking turns (pipeline.py), so each part gets its best chunk.
Only the search uses the sub-questions; the answer prompt still gets
the original question.

Caveats:
- One extra LLM call per question. Off in PRODUCTION
  (Pipeline.decompose).
- Splits only what the question asks: a part it implies but doesn't
  ask (e.g. a probation limit behind "joined two months ago") is left
  to the search.
- Never use wording from the eval questions as an example in the rules.
"""

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from ams_assistant.config import LLM_MODEL, TEMPERATURE
from ams_assistant.llm_cache import get_llm_cache

MAX_PARTS = 3

DECOMPOSE_PROMPT = ChatPromptTemplate.from_template("""\
You prepare questions for search over the AMS company handbooks.

If the question asks more than one thing, split it into separate
questions, one per thing asked, at most 3. If it asks one thing, return
it unchanged.

Rules:
- Each question must stand on its own: repeat the office, country,
  grade, role, numbers and dates it needs from the original.
- Keep the user's key terms word for word.
- Only split what the question asks. Do not add topics or questions it
  does not ask.
- Do not answer the question.
- Return one question per line, with no numbering, bullets or
  explanation.

Examples:
Question: Where is the mailroom in Pune, and when is it open?
Where is the mailroom at the Pune office?
What are the mailroom opening hours at the Pune office?

Question: What is the printer quota for L2 employees?
What is the printer quota for L2 employees?

Question: {question}
""")


# A list marker or "Question:" the model may put before a line:
# "- ", "* ", "1. ", "2) ".
LINE_PREFIX = re.compile(r"^\s*(?:[-*]|\d+[.)]|Question:)\s*")


def to_parts(reply: str) -> list[str]:
    """The reply's non-empty lines without list markers, at most
    MAX_PARTS. An empty reply gives an empty list."""
    parts = [LINE_PREFIX.sub("", line).strip()
             for line in reply.splitlines()]
    return [part for part in parts if part][:MAX_PARTS]


def build_decomposer():
    """Return the chain: {"question"} -> list of sub-questions."""
    # cache: a question split before gets its saved split.
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE,
                     cache=get_llm_cache(LLM_MODEL, TEMPERATURE))
    return DECOMPOSE_PROMPT | llm | StrOutputParser() | to_parts
