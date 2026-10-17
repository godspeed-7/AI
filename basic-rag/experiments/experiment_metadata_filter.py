"""Experiment: what does a metadata filter do to vector search?

Searches one fixed question twice and prints both result lists:
    1. Normal vector search across all chunks.
    2. The same search restricted to chunks whose payload has
       source == "leave_policy_india.txt" and section_id == "4.1".
       Both conditions are needed: several documents have a 4.1.

A filter narrows the search to chunks matching their stored metadata,
before similarity ranking. This demo hard-codes the filter to show the
mechanism; a real pipeline would choose it from the question (e.g. a
leave type) or from the user (e.g. their payroll country).
"""

from qdrant_client.models import Filter, FieldCondition, MatchValue

from basic_rag.config import TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search

TARGET_SOURCE = "leave_policy_india.txt"
TARGET_SECTION_ID = "4.1"


def print_results(title, points):
    """Print rank, document, section, title, and the first 200
    characters of each result."""
    print(f"\n--- {title} ---")

    if not points:
        print("No matching chunks found.")
        return

    for rank, point in enumerate(points, start=1):
        payload = point.payload or {}

        print(f"\nRank: {rank}")
        print(f"Document: {payload.get('source', '')}")
        print(f"Section: {payload.get('section_id', '')}")
        print(f"Title: {payload.get('section_title', '')}")
        print(f"Text: {payload.get('text', '')[:200]}")


def main():
    """Embed one question and compare unfiltered vs filtered search."""
    question = (
        "How many unused annual-leave days "
        "can an India-based employee normally carry over?"
    )

    embedding = generate_embedding(question)

    client = get_client()

    try:
        # 1. Normal vector search
        normal_results = search(client, embedding, limit=TOP_K)

        print_results("Normal vector search", normal_results)

        # 2. Vector search restricted to one document's section
        # must = every condition has to match (like SQL AND).
        filtered_results = search(
            client,
            embedding,
            limit=TOP_K,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=TARGET_SOURCE),
                    ),
                    FieldCondition(
                        key="section_id",
                        match=MatchValue(value=TARGET_SECTION_ID),
                    ),
                ]
            ),
        )

        print_results(
            f"Filtered vector search: {TARGET_SOURCE} "
            f"section {TARGET_SECTION_ID}",
            filtered_results,
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
