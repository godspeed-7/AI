"""Experiment: does rewriting the question with an LLM improve
retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline    search with the original question
         Rewritten   search with the LLM's rewrite (rewriter.py)
     plus every question that flipped (miss -> hit, or hit -> miss)
     with its rewrite, so you can see why a score moved.

Strategy: same retriever and same scoring (ams_assistant/evaluation.py)
for both runs; only the search text differs.

Caveats:
- One LLM call per question; runs 4 at a time with .batch().
- Rewrites run in parallel, so a rerun can give slightly different
  wording for a few questions.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from ams_assistant.config import TOP_K
from ams_assistant.evaluation import (
    expected_keys,
    load_questions,
    print_comparison,
    score,
)
from ams_assistant.rewriter import build_rewriter
from ams_assistant.vector_store import get_vector_store


def main():
    """Score both runs and print the comparison."""
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in questions]
    retriever = get_vector_store().as_retriever(search_kwargs={"k": TOP_K})

    print(f"Rewriting {len(texts)} questions with the LLM...")
    # .batch() is .invoke() on a list, running up to 4 calls at once
    # (like Promise.all with a concurrency limit).
    rewrites = build_rewriter().batch(
        [{"question": text} for text in texts],
        config={"max_concurrency": 4},
    )

    print("Retrieving with original and rewritten questions...")
    baseline_docs = retriever.batch(texts)
    rewritten_docs = retriever.batch(rewrites)

    baseline = []
    rewritten = []

    for item, docs_a, docs_b in zip(questions, baseline_docs, rewritten_docs):
        expected = expected_keys(item["expected_source"])
        baseline.append(score(expected, docs_a))
        rewritten.append(score(expected, docs_b))

    unchanged = sum(r == t for r, t in zip(rewrites, texts))
    print(f"Questions returned unchanged: {unchanged}/{len(texts)}")

    print_comparison("Rewritten", questions, baseline, rewritten, rewrites)


if __name__ == "__main__":
    main()
