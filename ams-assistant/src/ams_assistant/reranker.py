"""Reranking: re-score vector-search candidates with a cross-encoder
and keep the best.

In:  the question + candidate Documents (CANDIDATE_K from the
     retriever, best first).
Out: rerank(question, docs) -> the TOP_K most relevant Documents, best
     first, each with its score in metadata["rerank_score"].

Strategy: the embedding model turns the question and each chunk into
separate vectors and compares them: fast, but it never reads the two
together. A cross-encoder reads each (question, chunk) pair at once and
scores how well the chunk answers it: more precise, but too slow for
every chunk, so it only re-scores what vector search already found.
Every score is saved in RERANK_CACHE_FILE, keyed by model + question
text + chunk text, so a pair is only ever scored once.

Caveats:
- It can only reorder candidates; a chunk outside CANDIDATE_K is never
  seen.
- RERANKER_MODEL reads at most 512 tokens per pair; our largest chunk
  (~1,500 characters, ~375 tokens) plus a question fits.
- The cache clears itself when a question, a chunk or RERANKER_MODEL
  changes (new key). Delete RERANK_CACHE_FILE by hand when scores can
  change without any text changing: a sentence-transformers upgrade,
  or a new CrossEncoder setting (e.g. max_length).
- Uses sentence-transformers (PyTorch) directly, not a LangChain
  wrapper (those need langchain-community and langchain-classic).
"""

import hashlib
import sqlite3
import threading
from functools import cache

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from ams_assistant.config import RERANK_CACHE_FILE, RERANKER_MODEL, TOP_K
from ams_assistant.tracing import doc_lines, traced

# The answer eval reranks from several threads (--workers); one
# connection is shared, so only one thread uses it at a time.
cache_lock = threading.Lock()
# The same for the model: two threads using it at once crash PyTorch's
# Mac GPU backend (a Metal "command buffer" assertion), and two first
# calls would load it twice. Scoring takes ~1 s against ~20 s for an
# answer, so waiting costs little.
model_lock = threading.Lock()


# Loading the model takes seconds, so load it once and reuse it.
# @cache remembers the return value after the first call.
@cache
def get_reranker() -> CrossEncoder:
    """Load the cross-encoder (from the local Hugging Face cache)."""
    return CrossEncoder(RERANKER_MODEL)


@cache
def get_score_cache() -> sqlite3.Connection:
    """Open the score cache (created on first use): one row per pair."""
    RERANK_CACHE_FILE.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(RERANK_CACHE_FILE, check_same_thread=False)
    db.execute("CREATE TABLE IF NOT EXISTS scores "
               "(key TEXT PRIMARY KEY, score REAL)")
    return db


def pair_key(question: str, chunk: str) -> str:
    """A short fingerprint (SHA-256) of model + question + chunk: any
    change to one of them gives a different key."""
    text = f"{RERANKER_MODEL}\n{question}\n{chunk}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cached_scores(question: str, docs: list[Document]) -> list[float]:
    """One score per doc: from the cache where saved, otherwise from the
    cross-encoder (and then saved)."""
    keys = [pair_key(question, doc.page_content) for doc in docs]
    db = get_score_cache()
    with cache_lock:
        marks = ",".join("?" * len(keys))
        known = dict(db.execute(
            f"SELECT key, score FROM scores WHERE key IN ({marks})", keys))

    missing = [i for i, key in enumerate(keys) if key not in known]
    if missing:
        # One relevance score per (question, chunk) pair; higher = better.
        with model_lock:
            new = get_reranker().predict(
                [(question, docs[i].page_content) for i in missing],
                show_progress_bar=False,
            )
        rows = [(keys[i], float(score)) for i, score in zip(missing, new)]
        with cache_lock:
            db.executemany("INSERT OR REPLACE INTO scores VALUES (?, ?)",
                           rows)
            db.commit()
        known.update(rows)

    return [known[key] for key in keys]


# In a traced agent run, its own step in Langfuse (tracing.py).
@traced("reranker", "span",
        show_input=lambda question, docs, k=TOP_K: {
            "search": question, "candidates": len(docs), "keep": k},
        show_output=doc_lines)
def rerank(
    question: str, docs: list[Document], k: int = TOP_K
) -> list[Document]:
    """Return the k Documents the cross-encoder scores highest."""
    if not docs:
        return []

    scores = cached_scores(question, docs)
    ranked = sorted(zip(docs, scores), key=lambda pair: pair[1], reverse=True)

    # Kept on each Document, as search() keeps the vector score, so a
    # trace (or a debug print) shows why it ranked where it did.
    for doc, score in ranked[:k]:
        doc.metadata["rerank_score"] = float(score)
    return [doc for doc, _score in ranked[:k]]
