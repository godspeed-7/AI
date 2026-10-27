"""Reranking: re-score vector-search candidates with a cross-encoder
and keep the best.

In:  the question + candidate Documents (CANDIDATE_K from the
     retriever, best first).
Out: rerank(question, docs) -> the TOP_K most relevant Documents, best
     first.

Strategy: the embedding model turns the question and each chunk into
separate vectors and compares them: fast, but it never reads the two
together. A cross-encoder reads each (question, chunk) pair at once and
scores how well the chunk answers it: more precise, but too slow for
every chunk, so it only re-scores what vector search already found.

Caveats:
- It can only reorder candidates; a chunk outside CANDIDATE_K is never
  seen.
- RERANKER_MODEL reads at most 512 tokens per pair; our largest chunk
  (~1,500 characters, ~375 tokens) plus a question fits.
- Uses sentence-transformers (PyTorch) directly, not a LangChain
  wrapper (those need langchain-community and langchain-classic).
"""

from functools import cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from ams_assistant.config import RERANKER_MODEL, TOP_K


# Loading the model takes seconds, so load it once and reuse it.
# @cache remembers the return value after the first call.
@cache
def get_reranker() -> CrossEncoder:
    """Load the cross-encoder (from the local Hugging Face cache)."""
    return CrossEncoder(RERANKER_MODEL)


def rerank(
    question: str, docs: list[Document], k: int = TOP_K
) -> list[Document]:
    """Return the k Documents the cross-encoder scores highest."""
    if not docs:
        return []

    # One relevance score per (question, chunk) pair; higher = better.
    scores = get_reranker().predict(
        [(question, doc.page_content) for doc in docs],
        show_progress_bar=False,
    )
    ranked = sorted(zip(docs, scores), key=lambda pair: pair[1], reverse=True)

    return [doc for doc, _score in ranked[:k]]
