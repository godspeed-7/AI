
import csv
import json
from urllib.request import Request, urlopen

from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import COLLECTION_NAME
from qdrant_client import QdrantClient
from basic_rag.logger import heading, info, success, error


EVALUATION_FILE = "documents/evaluation_questions.csv"
TOP_K = 3

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "gemma3:4b"


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    import re

    return set(re.findall(r"\d+(?:\.\d+)*", expected_source))


def rewrite_query(question: str) -> str:
    prompt = f"""
Rewrite the user's question into a concise search query for retrieving
relevant passages from an HR leave policy.

Preserve the original meaning and intent.
Do not answer the question.
Do not invent facts or assume an answer.
Return only the rewritten search query.

Original question: {question}
"""

    request_data = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
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

    rewritten = result["response"].strip()

    if not rewritten:
        raise ValueError("Ollama returned an empty rewritten query.")

    return rewritten


def evaluate_retrieval(
    client: QdrantClient,
    questions: list[dict],
    use_rewriting: bool,
) -> dict:
    hits = 0
    recall_sum = 0.0
    mrr_sum = 0.0
    failures = []

    for index, item in enumerate(questions, start=1):
        original_question = item["question"]
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        if use_rewriting:
            search_query = rewrite_query(original_question)
        else:
            search_query = original_question

        query_embedding = generate_embedding(search_query)

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=TOP_K,
            with_payload=True,
        ).points

        # Preserve ranking order for MRR.
        retrieved_ids = [
            point.payload.get("section_id", "").strip()
            for point in results
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

        if not matched_ids:
            failures.append({
                "question": original_question,
                "search_query": search_query,
                "expected_source": expected_source,
                "retrieved_ids": retrieved_ids,
            })

        mode = "Rewritten" if use_rewriting else "Original"
        print(
            f"[{index}/{len(questions)}] {mode} query evaluated: "
            f"{original_question}"
        )

        if use_rewriting:
            print(f"    Search query: {search_query}")

    total = len(questions)

    return {
        "total": total,
        "hits": hits,
        "hit_rate": hits / total * 100 if total else 0.0,
        "recall": recall_sum / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
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

    if result["failures"]:
        print("\nFailed questions:")
        for failure in result["failures"]:
            print(f"- {failure['question']}")
            print(f"  Expected: {failure['expected_source']}")
            print(f"  Retrieved: {failure['retrieved_ids']}")
            if "search_query" in failure:
                print(f"  Rewritten query: {failure['search_query']}")


def main():
    heading("QUERY REWRITING EVALUATION")

    questions = load_questions(EVALUATION_FILE)
    client = QdrantClient(url="http://localhost:6333")

    info(f"Evaluation questions: {len(questions)}")
    info(f"Embedding model: all-minilm")
    info(f"Rewrite model: {LLM_MODEL}")
    info(f"Retrieving top {TOP_K} chunks per question")

    print("\nRunning baseline with original questions...")
    baseline = evaluate_retrieval(client, questions, use_rewriting=False)

    print("\nRunning experiment with rewritten questions...")
    rewritten = evaluate_retrieval(client, questions, use_rewriting=True)

    print_summary("BASELINE: ORIGINAL QUESTIONS", baseline)
    print_summary("EXPERIMENT: REWRITTEN QUESTIONS", rewritten)

    heading("METRIC COMPARISON")

    for metric in ("hit_rate", "recall", "mrr"):
        before = baseline[metric]
        after = rewritten[metric]
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


if __name__ == "__main__":
    main()
