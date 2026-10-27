"""Retrieval evaluation: does the retriever find the right policy
section?

In:  ams-data/evaluation_questions.csv; each answerable question lists
     its expected sections as "document#section" (e.g.
     "leave_policy_india.txt#4.1").
Out: Hit Rate, Recall and MRR (all "@TOP_K"), computed exactly as in
     basic-rag/evals/evaluate_retrieval.py, plus the questions that
     missed. No LLM is involved, so it takes seconds.

Strategy: our chunks carry only "source", not a section number. So a
chunk's sections are read from its text: every heading line in it
("4. ANNUAL LEAVE CARRY-OVER", "4.1 Standard carry-over limit") gives
one, e.g. {"leave_policy_india.txt#4", "leave_policy_india.txt#4.1"}.
The scoring lives in ams_assistant/evaluation.py, shared with
experiments/.

Caveats:
- A chunk that continues a section without repeating its heading has
  no section, so it never counts as a hit, even when it holds the
  answer. A chunk that only has a heading at its end still counts.
  The scores are therefore close to, not equal to, basic-rag's.
- Unanswerable questions (no expected section) are skipped.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from ams_assistant.config import TOP_K
from ams_assistant.evaluation import (
    expected_keys,
    load_questions,
    score,
    summarize,
)
from ams_assistant.vector_store import get_vector_store


def main():
    """Score the retriever on every question and print the metrics."""
    # Only questions with an expected source can be scored.
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    retriever = get_vector_store().as_retriever(search_kwargs={"k": TOP_K})

    print(f"Scoring {len(questions)} questions, top {TOP_K} chunks each...")

    scores = []
    failures = []

    for item in questions:
        docs = retriever.invoke(item["question"])
        result = score(expected_keys(item["expected_source"]), docs)
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
