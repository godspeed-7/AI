"""Hypothetical questions: an LLM writes the questions a chunk answers,
so search can match a user's question against questions, not policy
text.

In:  {"chunk": <one chunk's text>}
Out: build_question_writer().invoke(...) -> a list of up to
     NUM_HYPOTHETICAL_QUESTIONS questions (strings).

Strategy: the LLM reads only the chunk (unlike contextual retrieval,
no whole handbook), and is asked for everyday wording rather than the
section's formal terms, because that gap is what dense search misses
("switch teams" vs "apply for a job in another team").

Caveats:
- One LLM call per chunk, at ingestion only.
- gemma3:4b can write generic questions ("What does this section
  cover?"): read a sample before trusting them. The prompt has no
  examples, so no eval-question wording can leak in.
"""

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from ams_assistant.config import (
    LLM_MODEL,
    NUM_HYPOTHETICAL_QUESTIONS,
    TEMPERATURE,
)


QUESTIONS_PROMPT = ChatPromptTemplate.from_template("""\
Here is one section of the AMS company handbooks:

<section>
{chunk}
</section>

Write {count} different questions that an AMS employee might ask and \
that this section answers. Write them the way people really type into \
a chat: short, everyday words, not the section's formal terms. Each \
question must be about something this section actually says.

Return only the questions, one per line, with no numbering and no \
answers.
""")


def parse_questions(text: str) -> list[str]:
    """Split the reply into questions: one per line, without list
    markers ("1.", "-", "*"), keeping at most the requested count."""
    questions = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line).strip()
        if line:
            questions.append(line)
    return questions[:NUM_HYPOTHETICAL_QUESTIONS]


def build_question_writer():
    """Return the chain: {"chunk"} -> list of questions."""
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)
    prompt = QUESTIONS_PROMPT.partial(count=str(NUM_HYPOTHETICAL_QUESTIONS))

    # A plain function in a chain becomes a step too (like rewriter.py's
    # str.strip): the reply's text goes in, a list comes out.
    return prompt | llm | StrOutputParser() | parse_questions
