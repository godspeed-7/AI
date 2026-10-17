"""Rerank retrieved chunks with a cross-encoder (experiments only).

In:  the question + candidate chunks from vector search (CANDIDATE_K).
Out: the best top_n chunks as (chunk, score) pairs, highest first.

Strategy: the embedding model embeds question and chunk separately:
fast, but less precise. A cross-encoder reads them together and scores
relevance directly: more precise, but too slow to run on every chunk,
so it only re-scores the candidates vector search already found.

Caveats:
- It can only reorder candidates, never find a chunk that vector
  search missed.
- Needs sentence-transformers (PyTorch); RERANKER_MODEL is downloaded
  from Hugging Face on first use.
"""

from sentence_transformers import CrossEncoder

from basic_rag.config import RERANKER_MODEL

# Loading the model takes seconds, so load it once and reuse it.
_reranker = None


def get_reranker() -> CrossEncoder:
    """Load and cache the cross-encoder reranker."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def rerank_chunks(
    question: str,
    chunks: list,
    top_n: int = 3,
    model: CrossEncoder | None = None,
) -> list[tuple[object, float]]:
    """Return (chunk, relevance_score) pairs sorted highest-first.

    `chunks` are Qdrant points (from vector_store.search). Pass `model`
    to reuse an already-loaded cross-encoder; otherwise the cached one
    is used. Higher scores mean more relevant.
    """
    if not chunks or top_n <= 0:
        return []

    active_model = model or get_reranker()
    candidates = []
    model_inputs = []

    # Build (question, chunk text) pairs, skipping chunks with no text.
    for chunk in chunks:
        payload = chunk.payload or {}
        text = str(payload.get("text", "")).strip()
        if text:
            candidates.append(chunk)
            model_inputs.append((question, text))

    if not candidates:
        return []

    # Score all pairs in one call (processed in batches of 16).
    scores = active_model.predict(
        model_inputs,
        batch_size=16,
        show_progress_bar=False,
    )
    # Pair each chunk with its score and sort best-first.
    ranked = sorted(
        zip(candidates, [float(score) for score in scores]),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:top_n]
