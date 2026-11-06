"""Retrieval evaluation: does the retriever find the right policy
section?

In:  ams-data/evaluation_questions.csv; each answerable question lists
     its expected sections as "document#section" (e.g.
     "employee_handbook.txt#4.4.1"), and optionally other sections that
     state the same answer (also_correct).
Out: Hit Rate, Recall and MRR (all "@TOP_K"), computed as in
     basic-rag/evals/evaluate_retrieval.py, plus the questions that
     missed. No LLM is involved; with the reranker's saved scores
     (reranker.py) it takes seconds, about 6 minutes without them.

Strategy: retrieval is PRODUCTION (pipeline.py), the same as query.py
and the answer eval, so this scores what the app really retrieves.
A chunk's sections are read from its text: every heading
line in it ("4.4 ANNUAL LEAVE CARRY-OVER", "4.4.1 Standard carry-over
limit") gives one, e.g. {"employee_handbook.txt#4.4",
"employee_handbook.txt#4.4.1"}. The scoring lives in
ams_assistant/evaluation.py, shared with experiments/.

Caveats:
- A chunk with no heading line never counts as a hit, even when it
  holds the answer.
- An also_correct section counts as finding the expected section it
  stands in for. basic-rag ignores that column, so its scores are
  stricter than these.
- Unanswerable questions (no expected section) are skipped.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from ams_assistant.config import TOP_K
from ams_assistant.evaluation import (
    expected_groups,
    load_questions,
    score,
    summarize,
)
from ams_assistant.pipeline import PRODUCTION, retrieve


def main():
    """Score the retriever on every question and print the metrics."""
    # Only questions with an expected source can be scored.
    questions = [q for q in load_questions() if q["expected_source"].strip()]

    print(f"Pipeline: {PRODUCTION}")
    print(f"Scoring {len(questions)} questions, top {TOP_K} chunks each...")
    found = retrieve([item["question"] for item in questions], PRODUCTION)

    scores = []
    failures = []

    for item, docs in zip(questions, found):
        result = score(expected_groups(item), docs)
        scores.append(result)

        if not result["hit"]:
            failures.append((item, docs, result["keys_per_chunk"]))

    summary = summarize(scores)
    print(
        f"\nHit Rate@{TOP_K} : {summary['hit_rate']:.2f}% "
        f"({summary['hits']}/{summary['total']})"
    )
    print(f"Recall@{TOP_K}   : {summary['recall']:.4f}")
    print(f"MRR@{TOP_K}      : {summary['mrr']:.4f}")

    print(f"\nMissed questions ({len(failures)}):")

    for index, (item, docs, keys_per_chunk) in enumerate(failures, start=1):
        print(f"\n{index}. {item['question']}")
        print(f"   Expected : {item['expected_source']}")

        for rank, (doc, keys) in enumerate(zip(docs, keys_per_chunk), 1):
            # "(no heading)" = a continuation chunk; see Caveats.
            found = ", ".join(sorted(keys)) or "(no heading)"
            print(f"   [{rank}] {doc.metadata['source']}: {found}")


if __name__ == "__main__":
    main()
