"""The RAG chain: question in, retrieved chunks + answer out.

In:  a question string.
Out: build_chain().invoke(question) -> {"question": str,
     "docs": list[Document], "answer": AIMessage}.

Strategy: the same three query steps as before (retrieve -> prompt ->
generate), wired once with LCEL's | so callers make one invoke() call.
query.py and the evals both import this, so they always run the same
pipeline. Retrieval is pipeline.py's retrieve(), the same one the
experiments score, with the techniques PRODUCTION switches on.

Caveats:
- Each retrieved Document carries its vector similarity in
  metadata["score"] (cosine: higher = closer). Scores bunch together
  (~0.6-0.75 here), so compare gaps between chunks, not absolutes.
- No StrOutputParser at the end: the answer stays an AIMessage, so the
  token counts (usage_metadata) survive. Read the text with .content.
"""

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from ams_assistant.config import LLM_MODEL, TEMPERATURE
from ams_assistant.llm_cache import get_llm_cache
from ams_assistant.pipeline import PRODUCTION, Pipeline, retrieve
from ams_assistant.prompts import PROMPT, format_docs


def build_chain(pipeline: Pipeline = PRODUCTION):
    """Connect to Qdrant and Ollama and return the ready-to-run chain,
    retrieving with `pipeline` (default: what the app runs)."""
    # Step 1: Retrieve: question -> the closest Documents. A plain
    # function in a chain becomes a step too.
    def retriever(question: str) -> list[Document]:
        return retrieve([question], pipeline)[0]

    # cache: the same question with the same chunks gets its saved
    # answer (llm_cache.py) instead of a new LLM call.
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE,
                     cache=get_llm_cache())

    # Steps 2 + 3: Prompt and Generate. Receives {"question", "docs"},
    # adds "context" (the labelled chunks), fills PROMPT, calls the LLM.
    generate = (
        RunnablePassthrough.assign(context=lambda x: format_docs(x["docs"]))
        | PROMPT
        | llm
    )

    # A dict in a chain runs each value on the same input (here: the
    # question) and collects the results under its keys. Then .assign
    # keeps those keys and adds "answer", so the chunks come back too.
    return (
        {"question": RunnablePassthrough(), "docs": retriever}
        | RunnablePassthrough.assign(answer=generate)
    )
