
import csv
import json
import re
import time
from urllib.request import Request, urlopen

from qdrant_client import QdrantClient

from basic_rag.config import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EVALUATION_FILE,
    LLM_MODEL,
    OLLAMA_GENERATE_URL,
    QDRANT_URL,
    TOP_K,
)
from basic_rag.embedder import generate_embedding
from basic_rag.logger import heading, info, success, error


NUM_ALTERNATIVES = 2


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)*", expected_source))


def expand_query(question: str) -> list[str]:
    """Generate alternative search queries without answering the question."""
    prompt = f"""
You generate alternative search queries for semantic search over an
HR leave policy.

Generate exactly {NUM_ALTERNATIVES} alternative ways to search for
the information requested in the user's question.

Rules:
- Preserve the original question's intent.
- Preserve specific leave categories, numbers, dates, and conditions.
- Use different but relevant wording where useful.
- Do not answer the question.
- Do not invent policy facts.
- Keep each query concise.
- Do not simply repeat the original question.
- Return only a valid JSON array of strings.

Original question:
{question}
"""

    request_data = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    request = Request(
        OLLAMA_GENERATE_URL,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))

    response_text = result.get("response", "").strip()

    if not response_text:
        raise ValueError("Ollama returned empty query expansions.")

    parsed = json.loads(response_text)

    # Accept either a JSON array or an object containing a query array.
    if isinstance(parsed, dict):
        alternatives = parsed.get("queries", [])
    elif isinstance(parsed, list):
        alternatives = parsed
    else:
        raise ValueError("Unexpected query expansion response format.")

    # Remove empty queries and duplicates while preserving order.
    unique_queries = []
    seen = {question.strip().casefold()}

    for query in alternatives:
        if not isinstance(query, str):
            continue

        query = query.strip().strip('"').strip()

        if query and query.casefold() not in seen:
            unique_queries.append(query)
            seen.add(query.casefold())

        if len(unique_queries) == NUM_ALTERNATIVES:
            break

    if not unique_queries:
        raise ValueError("No valid alternative queries were generated.")

    return unique_queries


def retrieve_chunks(client: QdrantClient, query: str) -> list:
    query_embedding = generate_embedding(query)

    return client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=TOP_K,
        with_payload=True,
    ).points


def evaluate_retrieval(
    client: QdrantClient,
    questions: list[dict],
    use_expansion: bool,
) -> dict:
    hits = 0
    recall_sum = 0.0
    mrr_sum = 0.0
    failures = []
    start_time = time.perf_counter()

    for index, item in enumerate(questions, start=1):
        question = item["question"].strip()
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        print(f"\n[{index}/{len(questions)}] {question}")

        if use_expansion:
            alternatives = expand_query(question)
            queries = [question] + alternatives

            print("    Expanded queries:")
            for query in alternatives:
                print(f"      - {query}")
        else:
            queries = [question]

        # Merge results and retain each Qdrant point only once.
        # Best rank comes first; ties preserve query order.
        unique_points = {}

        for query_index, search_query in enumerate(queries):
            results = retrieve_chunks(client, search_query)

            for rank, point in enumerate(results, start=1):
                if not point.payload:
                    continue

                point_id = point.id
                candidate = {
                    "point": point,
                    "rank": rank,
                    "query_index": query_index,
                }

                existing = unique_points.get(point_id)

                if existing is None or (
                    rank, query_index
                ) < (
                    existing["rank"], existing["query_index"]
                ):
                    unique_points[point_id] = candidate

        # Rank unique chunks by their best rank across searches.
        ranked_candidates = sorted(
            unique_points.values(),
            key=lambda candidate: (
                candidate["rank"],
                candidate["query_index"],
            ),
        )

        final_points = [
            candidate["point"]
            for candidate in ranked_candidates[:TOP_K]
        ]

        retrieved_ids = [
            point.payload.get("section_id", "").strip()
            for point in final_points
            if point.payload
            and point.payload.get("section_id", "").strip()
        ]

        retrieved_id_set = set(retrieved_ids)
        matched_ids = expected_ids & retrieved_id_set

        if matched_ids:
            hits += 1

        question_recall = (
            len(matched_ids) / len(expected_ids)
            if expected_ids
            else 0.0
        )
        recall_sum += question_recall

        reciprocal_rank = 0.0

        for rank, section_id in enumerate(retrieved_ids, start=1):
            if section_id in expected_ids:
                reciprocal_rank = 1.0 / rank
                break

        mrr_sum += reciprocal_rank

        print(f"    Expected sections : {sorted(expected_ids)}")
        print(f"    Retrieved sections: {retrieved_ids}")

        if not matched_ids:
            failures.append({
                "question": question,
                "expected_source": expected_source,
                "expected_ids": sorted(expected_ids),
                "retrieved_ids": retrieved_ids,
            })
            error("Expected source not found.")
        else:
            success(f"Matched sections: {sorted(matched_ids)}")

    total = len(questions)
    elapsed = time.perf_counter() - start_time

    return {
        "total": total,
        "hits": hits,
        "hit_rate": hits / total * 100 if total else 0.0,
        "recall": recall_sum / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
        "elapsed": elapsed,
        "failures": failures,
    }


def print_summary(label: str, result: dict):
    heading(label)

    print(f"Total questions : {result['total']}")
    print(f"Source found    : {result['hits']}")
    print(f"Source missing  : {result['total'] - result['hits']}")
    print(f"Hit Rate@{TOP_K}   : {result['hit_rate']:.2f}%")
    print(f"Recall@{TOP_K}      : {result['recall']:.4f}")
    print(f"MRR@{TOP_K}         : {result['mrr']:.4f}")
    print(f"Total time      : {result['elapsed']:.2f} seconds")

    if result["failures"]:
        print("\nQuestions with no expected source in the final top 3:")

        for failure in result["failures"]:
            print(f"- {failure['question']}")
            print(f"  Expected: {failure['expected_ids']}")
            print(f"  Retrieved: {failure['retrieved_ids']}")


def print_comparison(baseline: dict, expanded: dict):
    heading("BASELINE VS QUERY EXPANSION")

    for metric in ("hit_rate", "recall", "mrr"):
        before = baseline[metric]
        after = expanded[metric]

        print(
            f"{metric.upper()}@{TOP_K}: "
            f"{before:.4f} -> {after:.4f} "
            f"(change: {after - before:+.4f})"
        )

    print(
        f"Execution time: {baseline['elapsed']:.2f}s -> "
        f"{expanded['elapsed']:.2f}s"
    )


def main():
    heading("QUERY EXPANSION EVALUATION")

    questions = load_questions(EVALUATION_FILE)

    if not questions:
        error(f"No evaluation questions found in {EVALUATION_FILE}")
        return

    client = QdrantClient(url=QDRANT_URL)

    try:
        info(f"Evaluation questions: {len(questions)}")
        info(f"Expansion model: {LLM_MODEL}")
        info(f"Embedding model: {EMBEDDING_MODEL}")
        info(f"Alternative queries per question: {NUM_ALTERNATIVES}")
        info(f"Final result limit: {TOP_K} unique chunks")

        print("\nRunning baseline...")
        baseline = evaluate_retrieval(
            client, questions, use_expansion=False
        )

        print("\nRunning query expansion experiment...")
        expanded = evaluate_retrieval(
            client, questions, use_expansion=True
        )

        print_summary("BASELINE: ORIGINAL QUESTIONS", baseline)
        print_summary("EXPERIMENT: QUERY EXPANSION", expanded)
        print_comparison(baseline, expanded)

    finally:
        client.close()


if __name__ == "__main__":
    main()
