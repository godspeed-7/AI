"""The RAG chain: question in, retrieved chunks + answer out.

In:  a question string.
Out: build_chain().invoke(question) -> {"question": str,
     "docs": list[Document], "answer": AIMessage}.

Strategy: the same three query steps as before (retrieve -> prompt ->
generate), wired once with LCEL's | so callers make one invoke() call.
query.py and the evals both import this, so they always run the same
pipeline.

Caveats:
- Each retrieved Document carries its vector similarity in
  metadata["score"] (cosine: higher = closer). Scores bunch together
  (~0.6-0.75 here), so compare gaps between chunks, not absolutes.
- No StrOutputParser at the end: the answer stays an AIMessage, so the
  token counts (usage_metadata) survive. Read the text with .content.
- use_reranker=True is an experiment switch (reranker.py), off by
  default; query.py doesn't use it.
"""

from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from ams_assistant.config import CANDIDATE_K, LLM_MODEL, TEMPERATURE, TOP_K
from ams_assistant.prompts import PROMPT, format_docs
from ams_assistant.vector_store import get_vector_store


def build_chain(use_reranker: bool = False):
    """Connect to Qdrant and Ollama and return the ready-to-run chain.

    use_reranker=True fetches CANDIDATE_K chunks and keeps the TOP_K the
    cross-encoder scores highest, instead of the search's own TOP_K.
    """
    # Step 1: Retrieve: question -> the closest Documents.
    store = get_vector_store()

    def search(question: str, k: int) -> list[Document]:
        """Vector search that keeps each score (as_retriever() would
        drop it) in doc.metadata["score"]."""
        results = store.similarity_search_with_score(question, k=k)
        for doc, score in results:
            doc.metadata["score"] = score
        return [doc for doc, _score in results]

    # A plain function in a chain becomes a step too.
    if use_reranker:
        # Imported here, not at the top: it loads PyTorch, which takes
        # seconds and isn't needed when the reranker is off.
        from ams_assistant.reranker import rerank

        def retriever(question: str):
            return rerank(question, search(question, CANDIDATE_K))
    else:
        def retriever(question: str):
            return search(question, TOP_K)

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
