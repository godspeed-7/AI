"""The RAG chain: question in, retrieved chunks + answer out.

In:  a question string.
Out: build_chain().invoke(question) -> {"question": str,
     "docs": list[Document], "answer": AIMessage}.

Strategy: the same three query steps as before (retrieve -> prompt ->
generate), wired once with LCEL's | so callers make one invoke() call.
query.py and (later) the evals both import this, so they always run
the same pipeline.

Caveats:
- as_retriever() returns Documents without their similarity scores.
- No StrOutputParser at the end: the answer stays an AIMessage, so the
  token counts (usage_metadata) survive. Read the text with .content.
"""

from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from ams_assistant.config import LLM_MODEL, TEMPERATURE, TOP_K
from ams_assistant.prompts import PROMPT, format_docs
from ams_assistant.vector_store import get_vector_store


def build_chain():
    """Connect to Qdrant and Ollama and return the ready-to-run chain."""
    # Step 1: Retrieve. A retriever is the vector store wrapped as a
    # Runnable: invoke(question) -> the TOP_K closest Documents.
    retriever = get_vector_store().as_retriever(search_kwargs={"k": TOP_K})
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)

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
