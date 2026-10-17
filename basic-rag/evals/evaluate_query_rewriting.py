import csv
import json
from urllib.request import Request, urlopen

from basic_rag.config import (
    EMBEDDING_MODEL,
    EVALUATION_FILE,
    LLM_MODEL,
    OLLAMA_GENERATE_URL,
    TOP_K,
)
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search
from qdrant_client import QdrantClient
from basic_rag.logger import heading, info, success, error


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    import re

    return set(re.findall(r"\d+(?:\.\d+)*", expected_source))


def rewrite_query(question: str) -> str:
    prompt = f"""
You rewrite questions for semantic search over an HR leave policy.

Your job is to make the question self-contained and easy to match to
the relevant policy passage, while preserving exactly what the user is
asking.

Rules:
- Preserve the user's intent and the specific leave category.
- Preserve any numbers, dates, eligibility details, and conditions in
  the original question.
- If the question refers to something ambiguous such as "it", "them",
  or "those days", clarify it only when the meaning is supported by the
  question itself. Do not guess missing context.
- Include useful policy terms that are clearly implied by the question.
- Do not answer the question.
- Do not add policy facts, assume an answer, or broaden the question.
- Keep the rewritten query concise, preferably one sentence.
- Return only the rewritten query, with no explanation or quotation marks.

Original question:
{question}

Rewritten search query:
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

    rewritten = result.get("response", "").strip()
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
    details = []

    for index, item in enumerate(questions, start=1):
        original_question = item["question"].strip()
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        if use_rewriting:
            search_query = rewrite_query(original_question)
        else:
            search_query = original_question

        query_embedding = generate_embedding(search_query)

        results = search(client, query_embedding, limit=TOP_K)

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

        detail = {
            "question": original_question,
            "search_query": search_query,
            "expected_source": expected_source,
            "expected_ids": sorted(expected_ids),
            "retrieved_ids": retrieved_ids,
            "matched_ids": sorted(matched_ids),
            "recall": question_recall,
            "reciprocal_rank": reciprocal_rank,
        }
        details.append(detail)

        if not matched_ids:
            failures.append(detail)

        mode = "Rewritten" if use_rewriting else "Original"
        print(f"[{index}/{len(questions)}] {mode} query evaluated:")
        print(f"    Original: {original_question}")
        if use_rewriting:
            print(f"    Rewritten: {search_query}")
        print(f"    Expected sections: {sorted(expected_ids)}")
        print(f"    Retrieved sections: {retrieved_ids}")
        print(f"    Matched sections: {sorted(matched_ids)}")

    total = len(questions)

    return {
        "total": total,
        "hits": hits,
        "hit_rate": hits / total * 100 if total else 0.0,
        "recall": recall_sum / total if total else 0.0,
        "mrr": mrr_sum / total if total else 0.0,
        "failures": failures,
        "details": details,
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
        print("\nQuestions with no expected source retrieved:")
        for failure in result["failures"]:
            print(f"- {failure['question']}")
            print(f"  Expected: {failure['expected_source']}")
            print(f"  Retrieved: {failure['retrieved_ids']}")
            if failure["search_query"] != failure["question"]:
                print(f"  Search query: {failure['search_query']}")


def print_comparison(baseline: dict, rewritten: dict):
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

    if (
        rewritten["hit_rate"] > baseline["hit_rate"]
        and rewritten["recall"] >= baseline["recall"]
        and rewritten["mrr"] >= baseline["mrr"]
    ):
        success("Rewriting improved Hit Rate without reducing Recall or MRR.")
    elif (
        rewritten["hit_rate"] == baseline["hit_rate"]
        and rewritten["recall"] == baseline["recall"]
        and rewritten["mrr"] == baseline["mrr"]
    ):
        info("No measured retrieval difference. Inspect rewritten queries before deciding.")
    else:
        info("Results are mixed or lower. Inspect the rewritten queries before adopting rewriting.")


def main():
    heading("QUERY REWRITING EVALUATION")

    questions = load_questions(EVALUATION_FILE)
    if not questions:
        error(f"No evaluation questions found in {EVALUATION_FILE}")
        return

    client = get_client()

    info(f"Evaluation questions: {len(questions)}")
    info(f"Embedding model: {EMBEDDING_MODEL}")
    info(f"Rewrite model: {LLM_MODEL}")
    info(f"Retrieving top {TOP_K} chunks per question")

    print("\nRunning baseline with original questions...")
    baseline = evaluate_retrieval(client, questions, use_rewriting=False)

    print("\nRunning experiment with rewritten questions...")
    rewritten = evaluate_retrieval(client, questions, use_rewriting=True)

    print_summary("BASELINE: ORIGINAL QUESTIONS", baseline)
    print_summary("EXPERIMENT: REWRITTEN QUESTIONS", rewritten)
    print_comparison(baseline, rewritten)

    client.close()


if __name__ == "__main__":
    main()
