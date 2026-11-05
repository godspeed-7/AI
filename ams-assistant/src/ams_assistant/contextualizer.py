"""Contextual retrieval: an LLM writes one line that places a chunk
within its whole document, to be stored on top of the chunk.

In:  {"document": <a whole handbook>, "chunk": <one chunk's text>}
Out: build_contextualizer().invoke(...) -> an AIMessage: .content is
     the context, e.g. "From the Employee Handbook's Joining AMS
     chapter: probation length for India and US payroll employees.";
     .usage_metadata["input_tokens"] is the prompt's size.

Strategy: CONTEXT_PROMPT is Anthropic's Contextual Retrieval prompt
(September 2024), unchanged. Unlike the chunk header, which only
repeats headings, the LLM can bring in facts from elsewhere in the
document (e.g. "employees in Austin are on the US payroll").

Caveats:
- One LLM call per chunk, each with the whole handbook, so it runs at
  ingestion only. Ollama reuses the handbook part of the prompt when
  calls for the same handbook come one after another.
- CONTEXT_NUM_CTX must hold the largest handbook, or Ollama silently
  cuts its start; check input_tokens. gemma3:4b can still invent
  context: read the lines.
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from ams_assistant.config import CONTEXT_NUM_CTX, LLM_MODEL, TEMPERATURE


CONTEXT_PROMPT = ChatPromptTemplate.from_template("""\
<document>
{document}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{chunk}
</chunk>
Please give a short succinct context to situate this chunk within the \
overall document for the purposes of improving search retrieval of the \
chunk. Answer only with the succinct context and nothing else.
""")


def build_contextualizer():
    """Return the chain: {"document", "chunk"} -> AIMessage."""
    llm = ChatOllama(
        model=LLM_MODEL,
        temperature=TEMPERATURE,
        num_ctx=CONTEXT_NUM_CTX,
    )
    # No StrOutputParser: the caller also needs usage_metadata.
    return CONTEXT_PROMPT | llm


def one_line(text: str) -> str:
    """Collapse the LLM's reply to one line, so the context can't look
    like a heading line ("3.4 Probation") to the eval's scoring."""
    return " ".join(text.split())
