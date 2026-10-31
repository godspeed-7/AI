"""Experiment: does routing the question to its policy files first
improve retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline    search all chunks
         Routed      the LLM picks the files (router.py); search only
                     their chunks, or all chunks if it said "all"
     plus router accuracy (did the picked files include the expected
     ones?) and every question that flipped, with the route.

Strategy: same retriever and same scoring (ams_assistant/evaluation.py)
for both runs; only the filter differs. Router accuracy is reported
separately, so a miss can be blamed on the route or on the search.

Caveats:
- One LLM call per question; runs 4 at a time with .batch().
- A route that fails (a reply that doesn't fit Route) counts as "all".
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
from ams_assistant.router import Route, build_router, route_filter
from ams_assistant.vector_store import get_vector_store


def main():
    """Route every question, score both runs, and print the results."""
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in questions]
    store = get_vector_store()

    print(f"Routing {len(texts)} questions...")
    start = time.perf_counter()
    # return_exceptions=True: a failed route comes back as the error
    # instead of stopping the whole batch.
    routes = build_router().batch(
        [{"question": text} for text in texts],
        config={"max_concurrency": 4},
        return_exceptions=True,
    )
    print(f"Run time: routing {time.perf_counter() - start:.0f}s")

    routes = [
        route if isinstance(route, Route)
        else Route(reason=f"FAILED: {route}", files=["all"])
        for route in routes
    ]

    baseline = []
    routed = []
    accuracy = {"all": 0, "right": 0, "partly": 0, "wrong": 0}

    for item, text, route in zip(questions, texts, routes):
        expected = expected_keys(item["expected_source"])
        plain_docs = store.similarity_search(text, k=TOP_K)
        routed_docs = store.similarity_search(
            text, k=TOP_K, filter=route_filter(route)
        )
        baseline.append(score(expected, plain_docs))
        routed.append(score(expected, routed_docs))

        # "a.txt#4.1" -> "a.txt": which files the answer lives in.
        expected_files = {key.split("#")[0] for key in expected}
        picked = set(route.files)
        if route_filter(route) is None:
            accuracy["all"] += 1
        elif expected_files <= picked:
            accuracy["right"] += 1
        elif expected_files & picked:
            accuracy["partly"] += 1
        else:
            accuracy["wrong"] += 1

    print(f"\nRouter ({len(routes)} questions):")
    print(f"  all expected files picked : {accuracy['right']}")
    print(f"  some expected files picked: {accuracy['partly']}")
    print(f"  wrong files picked        : {accuracy['wrong']}")
    print(f"  said \"all\" (no filter)    : {accuracy['all']}")

    details = [
        f"{', '.join(route.files)} ({route.reason})" for route in routes
    ]
    print_comparison("Routed", questions, baseline, routed, details)


if __name__ == "__main__":
    main()
