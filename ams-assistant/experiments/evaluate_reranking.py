"""Experiment: does a cross-encoder reranker improve retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline    vector search returns the top TOP_K chunks
         Reranked    vector search returns CANDIDATE_K candidates,
                     the cross-encoder keeps the best TOP_K
                     (reranker.py)
     plus every question that flipped, and the run time of each.

Strategy: same retriever and same scoring (ams_assistant/evaluation.py)
for both runs. The reranked run takes the baseline's candidates from
the same search, so only the ordering differs.

Caveats:
- No LLM; the cross-encoder runs on the CPU/GPU in this process.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import time

from ams_assistant.config import CANDIDATE_K, TOP_K
from ams_assistant.evaluation import (
    expected_keys,
    load_questions,
    print_comparison,
    score,
)
from ams_assistant.reranker import get_reranker, rerank
from ams_assistant.vector_store import get_vector_store


def main():
    """Score both runs and print the comparison."""
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in questions]
    retriever = get_vector_store().as_retriever(
        search_kwargs={"k": CANDIDATE_K}
    )

    start = time.perf_counter()
    candidates = retriever.batch(texts)
    search_seconds = time.perf_counter() - start

    get_reranker()  # load the model first, so it isn't timed below

    print(f"Reranking {CANDIDATE_K} candidates for {len(texts)} questions...")
    start = time.perf_counter()
    reranked_docs = [
        rerank(text, docs) for text, docs in zip(texts, candidates)
    ]
    rerank_seconds = time.perf_counter() - start

    baseline = []
    reranked = []

    for item, docs, docs_b in zip(questions, candidates, reranked_docs):
        expected = expected_keys(item["expected_source"])
        # The search's own top TOP_K = the plain baseline.
        baseline.append(score(expected, docs[:TOP_K]))
        reranked.append(score(expected, docs_b))

    print(
        f"Run time: search {search_seconds:.0f}s, "
        f"reranking {rerank_seconds:.0f}s"
    )

    # For a flipped question, show where its new top chunks came from.
    details = [
        "new top from search ranks "
        + ", ".join(str(docs.index(doc) + 1) for doc in docs_b)
        for docs, docs_b in zip(candidates, reranked_docs)
    ]
    print_comparison("Reranked", questions, baseline, reranked, details)


if __name__ == "__main__":
    main()
