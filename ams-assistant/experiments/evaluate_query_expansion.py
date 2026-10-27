"""Experiment: does searching with several phrasings improve
retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline    search with the original question
         Expanded    search with the original + NUM_ALTERNATIVES
                     LLM phrasings (expander.py), results merged
     plus every question that flipped, with its alternatives, and the
     run time of each.

Strategy: same retriever and same scoring (ams_assistant/evaluation.py)
for both runs; only the queries searched differ.

Caveats:
- One LLM call per question; runs 4 at a time with .batch().
- Alternatives run in parallel, so a rerun can word a few differently.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import time

from ams_assistant.config import TOP_K
from ams_assistant.evaluation import (
    expected_keys,
    load_questions,
    print_comparison,
    score,
)
from ams_assistant.expander import build_expander, merge_results
from ams_assistant.vector_store import get_vector_store


def main():
    """Score both runs and print the comparison."""
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in questions]
    retriever = get_vector_store().as_retriever(search_kwargs={"k": TOP_K})

    start = time.perf_counter()
    baseline_docs = retriever.batch(texts)
    baseline_seconds = time.perf_counter() - start

    print(f"Expanding {len(texts)} questions with the LLM...")
    start = time.perf_counter()
    alternatives = build_expander().batch(
        [{"question": text} for text in texts],
        config={"max_concurrency": 4},
    )

    print("Retrieving with every phrasing and merging...")
    expanded_docs = []

    for text, alts in zip(texts, alternatives):
        # The original comes first, so it wins ties when merging.
        results = retriever.batch([text, *alts])
        expanded_docs.append(merge_results(results))

    expanded_seconds = time.perf_counter() - start

    baseline = []
    expanded = []

    for item, docs_a, docs_b in zip(questions, baseline_docs, expanded_docs):
        expected = expected_keys(item["expected_source"])
        baseline.append(score(expected, docs_a))
        expanded.append(score(expected, docs_b))

    print(
        f"Run time: baseline {baseline_seconds:.0f}s, "
        f"expanded {expanded_seconds:.0f}s"
    )

    details = [" | ".join(alts) for alts in alternatives]
    print_comparison("Expanded", questions, baseline, expanded, details)


if __name__ == "__main__":
    main()
