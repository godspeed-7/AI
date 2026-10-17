"""Rerank retrieved chunks with a cross-encoder (used by evals only).

Two kinds of model compare a question with a chunk:

  Bi-encoder (the embedding model)
      Embeds the question and the chunk separately, then compares the
      vectors. Fast, because chunk vectors are computed once at
      ingestion, but less precise.

  Cross-encoder (this module)
      Reads the question and the chunk together and outputs one
      relevance score. More precise, but must run once per
      (question, chunk) pair at query time, so it's too slow to score
      every chunk.

The usual pattern: vector search fetches a wide set of candidates
(CANDIDATE_K), the cross-encoder re-scores them, and the best TOP_K are
kept. Reranking can only reorder candidates; it can't find a chunk that
vector search missed.

Requires sentence-transformers (PyTorch). The model is downloaded from
Hugging Face on first use.
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
