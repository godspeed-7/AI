from sentence_transformers import CrossEncoder

from basic_rag.config import RERANKER_MODEL

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
    """Return (chunk, relevance_score) pairs sorted highest-first."""
    if not chunks or top_n <= 0:
        return []

    active_model = model or get_reranker()
    candidates = []
    model_inputs = []

    for chunk in chunks:
        payload = chunk.payload or {}
        text = str(payload.get("text", "")).strip()
        if text:
            candidates.append(chunk)
            model_inputs.append((question, text))

    if not candidates:
        return []

    scores = active_model.predict(
        model_inputs,
        batch_size=16,
        show_progress_bar=False,
    )
    ranked = sorted(
        zip(candidates, [float(score) for score in scores]),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:top_n]
