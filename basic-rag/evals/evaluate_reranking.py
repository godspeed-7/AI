"""Experiment: does a cross-encoder reranker improve retrieval?

Run from the basic-rag/ folder (no LLM needed; the reranker model is
downloaded from Hugging Face on the first run):
    uv run python evals/evaluate_reranking.py

Compares two retrieval flows on every evaluation question:
    Baseline   vector search returns the top TOP_K (3) chunks directly.
    Reranked   vector search returns CANDIDATE_K (20) candidates, the
               cross-encoder re-scores each one against the question,
               and the best TOP_K are kept.

Metrics: Hit Rate, Recall, and MRR @3, as defined in
evaluate_retrieval.py. See basic_rag/reranker.py for how a cross-encoder
differs from the embedding model.

Reranking can only reorder the 20 candidates; it can't recover a chunk
that vector search didn't fetch.
"""

import csv
import time

from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder

from basic_rag.config import (
    CANDIDATE_K,
    EMBEDDING_MODEL,
    EVALUATION_FILE,
    RERANKER_MODEL,
    TOP_K,
)
from basic_rag.embedder import generate_embedding
from basic_rag.logger import heading, info, error
from basic_rag.reranker import rerank_chunks
from basic_rag.vector_store import get_client, search


def load_questions(file_path: str) -> list[dict]:
    """Read the evaluation CSV into a list of row dicts."""
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    """Turn "a.txt#4.1; b.txt#2" into {"a.txt#4.1", "b.txt#2"}."""
    return {
        key.strip() for key in expected_source.split(";") if key.strip()
    }


def section_key(point) -> str:
    """Return a retrieved point's "document#section" key, or "" if the
    chunk has no section (text before a document's first heading)."""
    payload = point.payload or {}
    section_id = str(payload.get("section_id", "")).strip()
    if not section_id:
        return ""
    return f"{payload.get('source', '')}#{section_id}"


def calculate_metrics(details: list[dict]) -> dict:
    """Compute Hit Rate, Recall, and MRR from per-question results.

    Each item in `details` needs expected_ids (set) and retrieved_ids
    (list, best first). Returns the averages plus the failed questions.
    """
    total = len(details)
    hits = 0
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    failures = []

    for item in details:
        expected_ids = item["expected_ids"]
        retrieved_ids = item["retrieved_ids"]
        matched_ids = expected_ids & set(retrieved_ids)

        # Hit: at least one expected section was retrieved.
        if matched_ids:
            hits += 1

        # Recall: fraction of the expected sections that were retrieved.
        recall_sum += (
            len(matched_ids) / len(expected_ids) if expected_ids else 0.0
        )

        # Reciprocal rank: 1 / position of the first correct section.
        reciprocal_rank = 0.0
        for rank, section_id in enumerate(retrieved_ids, start=1):
            if section_id in expected_ids:
                reciprocal_rank = 1.0 / rank
                break
        reciprocal_rank_sum += reciprocal_rank

        if not matched_ids:
            failures.append({
                "question": item["question"],
                "expected_source": item["expected_source"],
                "retrieved_ids": retrieved_ids,
            })

    return {
        "total": total,
        "hits": hits,
        "hit_rate": hits / total * 100 if total else 0.0,
        "recall": recall_sum / total if total else 0.0,
        "mrr": reciprocal_rank_sum / total if total else 0.0,
        "failures": failures,
        "details": details,
    }


def evaluate_baseline(client: QdrantClient, questions: list[dict]) -> dict:
    """Current flow: Qdrant retrieves top 3, without reranking."""
    details = []

    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)
        embedding = generate_embedding(question)

        chunks = search(client, embedding, limit=TOP_K)

        # Section keys in rank order (best first), skipping blanks.
        retrieved_ids = [key for key in map(section_key, chunks) if key]
        details.append({
            "question": question,
            "expected_source": expected_source,
            "expected_ids": expected_ids,
            "retrieved_ids": retrieved_ids,
        })
        print(f"[Baseline {index}/{len(questions)}] {question}")
        print(f"    Retrieved sections: {retrieved_ids}")

    return calculate_metrics(details)


def evaluate_with_reranking(
    client: QdrantClient,
    questions: list[dict],
    reranker: CrossEncoder,
) -> dict:
    """Retrieve 20 candidates, rerank them, and keep the top 3."""
    details = []

    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)
        embedding = generate_embedding(question)

        # Step 1: wide first pass with vector search.
        candidates = search(client, embedding, limit=CANDIDATE_K)

        # Step 2: cross-encoder re-scores all candidates, keep the best.
        ranked = rerank_chunks(
            question=question,
            chunks=candidates,
            top_n=TOP_K,
            model=reranker,
        )
        # Step 3: record the result. ranked_sections keeps the reranker
        # scores so they can be printed below.
        retrieved_ids = [
            key for key in (section_key(point) for point, _score in ranked)
            if key
        ]
        details.append({
            "question": question,
            "expected_source": expected_source,
            "expected_ids": expected_ids,
            "retrieved_ids": retrieved_ids,
            "ranked_sections": [
                {
                    "section_id": section_key(point),
                    "section_title": str((point.payload or {}).get("section_title", "")),
                    "score": score,
                }
                for point, score in ranked
            ],
        })

        print(f"[Reranked {index}/{len(questions)}] {question}")
        for rank, item_detail in enumerate(details[-1]["ranked_sections"], start=1):
            print(
                f"    {rank}. Section {item_detail['section_id']} "
                f"(score={item_detail['score']:.4f}) "
                f"{item_detail['section_title']}"
            )
        print(f"    Expected sections: {sorted(expected_ids)}")

    return calculate_metrics(details)


def print_summary(label: str, result: dict) -> None:
    """Print one flow's metrics and the questions it missed."""
    heading(label)
    print(f"Questions   : {result['total']}")
    print(f"Hit Rate@{TOP_K} : {result['hit_rate']:.2f}%")
    print(f"Recall@{TOP_K}   : {result['recall']:.4f}")
    print(f"MRR@{TOP_K}      : {result['mrr']:.4f}")

    if result["failures"]:
        print("\nQuestions with no expected source in the final top 3:")
        for failure in result["failures"]:
            print(f"- {failure['question']}")
            print(f"  Expected: {failure['expected_source']}")
            print(f"  Retrieved: {failure['retrieved_ids']}")


def print_comparison(baseline: dict, reranked: dict) -> None:
    """Print each metric before -> after, with the difference."""
    heading("BASELINE VS RERANKING")
    for metric in ("hit_rate", "recall", "mrr"):
        before = baseline[metric]
        after = reranked[metric]
        difference = after - before
        if metric == "hit_rate":
            print(
                f"Hit Rate@{TOP_K}: {before:.2f}% -> {after:.2f}% "
                f"({difference:+.2f} percentage points)"
            )
        else:
            print(
                f"{metric.upper()}@{TOP_K}: {before:.4f} -> {after:.4f} "
                f"({difference:+.4f})"
            )


def main() -> None:
    """Run baseline, then reranked retrieval, and compare them."""
    heading("RERANKING EVALUATION")
    # Only questions with an expected source can be scored; the
    # unanswerable ones are skipped.
    questions = [
        q for q in load_questions(EVALUATION_FILE)
        if q["expected_source"].strip()
    ]
    if not questions:
        error(f"No evaluation questions found in {EVALUATION_FILE}")
        return

    client = get_client()
    try:
        info(f"Evaluation questions: {len(questions)}")
        info(f"Embedding model: {EMBEDDING_MODEL}")
        info(f"Reranker model: {RERANKER_MODEL}")
        info(f"Baseline: Qdrant top {TOP_K}")
        info(f"Reranking: Qdrant top {CANDIDATE_K}, then keep top {TOP_K}")

        # Step 1: baseline (plain vector search).
        print("\nRunning baseline evaluation...")
        baseline_start = time.perf_counter()
        baseline = evaluate_baseline(client, questions)
        baseline_seconds = time.perf_counter() - baseline_start

        # Step 2: load the reranker once (timed separately, since it's a
        # one-off cost, not a per-question cost).
        print("\nLoading cross-encoder model...")
        load_start = time.perf_counter()
        reranker = CrossEncoder(RERANKER_MODEL)
        info(f"Reranker loaded in {time.perf_counter() - load_start:.2f}s")

        # Step 3: reranked retrieval.
        print("\nRunning reranked evaluation...")
        rerank_start = time.perf_counter()
        reranked = evaluate_with_reranking(client, questions, reranker)
        rerank_seconds = time.perf_counter() - rerank_start

        # Step 4: report.
        print_summary("BASELINE: QDRANT TOP 3", baseline)
        print_summary("RERANKED: QDRANT TOP 20 -> TOP 3", reranked)
        print_comparison(baseline, reranked)

        heading("RUNTIME")
        print(f"Baseline evaluation: {baseline_seconds:.2f}s")
        print(f"Reranked evaluation: {rerank_seconds:.2f}s")
        info(
            "Reranking can reorder only the candidates retrieved by Qdrant; "
            "it cannot recover a relevant chunk outside those candidates."
        )
    except Exception as exc:
        error(f"Reranking evaluation failed: {exc}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
