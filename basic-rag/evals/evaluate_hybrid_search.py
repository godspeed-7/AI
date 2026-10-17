import csv
import re
import time

from rank_bm25 import BM25Okapi
from qdrant_client import QdrantClient

from basic_rag.embedder import generate_embedding
from basic_rag.logger import heading, info, error
from basic_rag.vector_store import COLLECTION_NAME

EVALUATION_FILE = "documents/evaluation_questions.csv"
QDRANT_URL = "http://localhost:6333"
CANDIDATE_K = 20
FINAL_K = 3
RRF_K = 60


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def tokenize(text: str) -> list[str]:
    """Simple lowercase word tokenization for this BM25 experiment."""
    return re.findall(r"\b[\w.]+\b", text.lower())


def extract_section_ids(expected_source: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)*", expected_source))


def section_id(point) -> str:
    return str((point.payload or {}).get("section_id", "")).strip()


def load_all_chunks(client: QdrantClient) -> list:
    """Read existing chunks from Qdrant; this does not modify the collection."""
    points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(batch)
        if offset is None:
            break
    return points


def calculate_metrics(details: list[dict]) -> dict:
    total = len(details)
    hits = 0
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    failures = []

    for item in details:
        expected_ids = item["expected_ids"]
        retrieved_ids = item["retrieved_ids"]
        matched_ids = expected_ids & set(retrieved_ids)
        if matched_ids:
            hits += 1
        recall_sum += len(matched_ids) / \
            len(expected_ids) if expected_ids else 0.0

        reciprocal_rank = 0.0
        for rank, retrieved_id in enumerate(retrieved_ids, start=1):
            if retrieved_id in expected_ids:
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
        "hit_rate": hits / total * 100 if total else 0.0,
        "recall": recall_sum / total if total else 0.0,
        "mrr": reciprocal_rank_sum / total if total else 0.0,
        "failures": failures,
    }


def evaluate_vector_baseline(client: QdrantClient, questions: list[dict]) -> dict:
    """Current flow: vector search returns only the final top 3."""
    details = []
    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        expected_source = item.get("expected_source", "").strip()
        embedding = generate_embedding(question)
        points = client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=FINAL_K,
            with_payload=True,
        ).points
        retrieved_ids = [sid for sid in map(section_id, points) if sid]
        details.append({
            "question": question,
            "expected_source": expected_source,
            "expected_ids": extract_section_ids(expected_source),
            "retrieved_ids": retrieved_ids,
        })
        print(f"[Vector {index}/{len(questions)}] {question}")
        print(f"    Sections: {retrieved_ids}")
    return calculate_metrics(details)


def reciprocal_rank_fusion(ranked_lists: list[list], k: int = RRF_K) -> list:
    """Fuse ranked Qdrant point lists, deduplicating by point ID."""
    scores = {}
    point_by_id = {}
    for ranked_list in ranked_lists:
        for rank, point in enumerate(ranked_list, start=1):
            key = str(point.id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            point_by_id[key] = point
    ordered = sorted(scores, key=scores.get, reverse=True)
    return [(point_by_id[key], scores[key]) for key in ordered]


def evaluate_hybrid(
    client: QdrantClient,
    questions: list[dict],
    corpus_points: list,
    bm25: BM25Okapi,
) -> dict:
    details = []
    corpus_ids = [str(point.id) for point in corpus_points]
    point_by_id = {str(point.id): point for point in corpus_points}

    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        expected_source = item.get("expected_source", "").strip()

        # Path A: semantic retrieval.
        embedding = generate_embedding(question)
        vector_candidates = client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=CANDIDATE_K,
            with_payload=True,
        ).points

        # Path B: lexical retrieval uses the original question text.
        bm25_scores = bm25.get_scores(tokenize(question))
        ranked_indexes = sorted(
            range(len(bm25_scores)),
            key=lambda idx: bm25_scores[idx],
            reverse=True,
        )
        keyword_candidates = [
            point_by_id[corpus_ids[idx]]
            for idx in ranked_indexes[:CANDIDATE_K]
            if bm25_scores[idx] > 0
        ]

        # RRF combines ranks, not the raw scores from either search.
        fused = reciprocal_rank_fusion([vector_candidates, keyword_candidates])
        final_points = [point for point, _score in fused[:FINAL_K]]
        retrieved_ids = [sid for sid in map(section_id, final_points) if sid]

        details.append({
            "question": question,
            "expected_source": expected_source,
            "expected_ids": extract_section_ids(expected_source),
            "retrieved_ids": retrieved_ids,
        })
        print(f"[Hybrid {index}/{len(questions)}] {question}")
        print(f"    Sections: {retrieved_ids}")
        print(f"    Expected: {sorted(extract_section_ids(expected_source))}")
    return calculate_metrics(details)


def print_summary(label: str, result: dict) -> None:
    heading(label)
    print(f"Questions   : {result['total']}")
    print(f"Hit Rate@{FINAL_K} : {result['hit_rate']:.2f}%")
    print(f"Recall@{FINAL_K}   : {result['recall']:.4f}")
    print(f"MRR@{FINAL_K}      : {result['mrr']:.4f}")
    if result["failures"]:
        print("\nQuestions with no expected source in the final top 3:")
        for failure in result["failures"]:
            print(f"- {failure['question']}")
            print(f"  Expected: {failure['expected_source']}")
            print(f"  Retrieved: {failure['retrieved_ids']}")


def main() -> None:
    heading("HYBRID SEARCH EVALUATION")
    questions = load_questions(EVALUATION_FILE)
    if not questions:
        error(f"No evaluation questions found in {EVALUATION_FILE}")
        return

    client = QdrantClient(url=QDRANT_URL)
    try:
        info(f"Evaluation questions: {len(questions)}")
        info(f"Qdrant collection: {COLLECTION_NAME}")
        info(f"Vector candidates: top {CANDIDATE_K}")
        info(f"BM25 candidates: top {CANDIDATE_K}")
        info(f"RRF constant: {RRF_K}")
        info("Reading existing chunks from Qdrant (read-only)...")

        corpus_points = [
            point for point in load_all_chunks(client)
            if (point.payload or {}).get("text")
        ]
        if not corpus_points:
            error("No text chunks found in the Qdrant collection.")
            return

        tokenized_corpus = [
            tokenize(str(point.payload.get("text", "")))
            for point in corpus_points
        ]
        bm25 = BM25Okapi(tokenized_corpus)
        info(f"BM25 index built in memory for {len(corpus_points)} chunks")

        print("\nRunning vector-only baseline...")
        start = time.perf_counter()
        baseline = evaluate_vector_baseline(client, questions)
        baseline_seconds = time.perf_counter() - start

        print("\nRunning hybrid retrieval...")
        start = time.perf_counter()
        hybrid = evaluate_hybrid(client, questions, corpus_points, bm25)
        hybrid_seconds = time.perf_counter() - start

        print_summary("BASELINE: VECTOR TOP 3", baseline)
        print_summary(
            "HYBRID: VECTOR TOP 20 + BM25 TOP 20 -> RRF TOP 3", hybrid)

        heading("BASELINE VS HYBRID")
        for metric in ("hit_rate", "recall", "mrr"):
            before, after = baseline[metric], hybrid[metric]
            difference = after - before
            if metric == "hit_rate":
                print(
                    f"Hit Rate@{FINAL_K}: {before:.2f}% -> {after:.2f}% "
                    f"({difference:+.2f} percentage points)"
                )
            else:
                print(
                    f"{metric.upper()}@{FINAL_K}: {before:.4f} -> {after:.4f} "
                    f"({difference:+.4f})"
                )

        heading("RUNTIME")
        print(f"Vector-only baseline: {baseline_seconds:.2f}s")
        print(f"Hybrid evaluation:    {hybrid_seconds:.2f}s")
        info("This script does not modify query.py or the Qdrant collection.")
    except Exception as exc:
        error(f"Hybrid search evaluation failed: {exc}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()
