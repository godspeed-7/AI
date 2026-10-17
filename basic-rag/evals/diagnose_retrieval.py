"""Diagnostic: why does section 7.1 rank where it does?

Run from the basic-rag/ folder (no LLM needed):
    uv run python evals/diagnose_retrieval.py

The question "Does the policy specify a fixed number of parental-leave
days?" should retrieve section 7.1 (parental leave). This script tries
the original wording and three rephrasings, and for each prints:
    - its cosine similarity with section 7.1's stored vector
    - the top 5 search results with their scores
    - where 7.1 ranked, or "outside top 5"

Useful for telling apart "the chunk is a poor match for this wording"
(low similarity) from "other chunks just scored slightly higher" (good
similarity, but a lower rank).
"""

from basic_rag.config import COLLECTION_NAME
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search
from qdrant_client import models


# The original evaluation question plus three ways of rephrasing it.
QUESTIONS = [
    {
        "label": "Original",
        "text": "Does the policy specify a fixed number of parental-leave days?",
    },
    {
        "label": "Alternative A",
        "text": "What determines an employee's parental-leave entitlement?",
    },
    {
        "label": "Alternative B",
        "text": "Which section explains parental-leave entitlement and its duration?",
    },
    {
        "label": "Alternative C",
        "text": "Are parental-leave entitlements defined by separate procedures?",
    },
]

# Deliberately wider than config.TOP_K to see near-miss ranks.
TOP_K = 5
TARGET_SECTION_ID = "7.1"


def get_target_section(client):
    """Fetch the first stored chunk of the target section, with its
    vector (search results don't include vectors by default)."""
    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="section_id",
                    match=models.MatchValue(value=TARGET_SECTION_ID),
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=True,
    )

    if not points:
        raise RuntimeError(
            f"Section {TARGET_SECTION_ID} was not found in Qdrant."
        )

    return points[0]


def cosine_similarity(vector_a, vector_b):
    """How closely two vectors point the same way: 1.0 = identical
    direction, 0 = unrelated. This is the measure Qdrant ranks by."""
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = sum(a * a for a in vector_a) ** 0.5
    norm_b = sum(b * b for b in vector_b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def main():
    """Compare each phrasing's similarity to 7.1 and its search rank."""
    client = get_client()

    print("Connected to Qdrant")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Retrieving top {TOP_K} chunks per question")

    # Step 1: get section 7.1's stored vector to compare against.
    target_point = get_target_section(client)
    target_vector = target_point.vector

    # Handle named vectors if the collection uses them.
    if isinstance(target_vector, dict):
        target_vector = target_vector.get("")

    if target_vector is None:
        raise RuntimeError("Could not read the stored Section 7.1 vector.")

    # Step 2: for each phrasing, measure similarity to 7.1 directly,
    # then run a normal search and see where 7.1 lands.
    for item in QUESTIONS:
        question = item["text"]
        question_embedding = generate_embedding(question)

        target_score = cosine_similarity(
            question_embedding,
            target_vector,
        )

        results = search(client, question_embedding, limit=TOP_K)

        print("\n" + "=" * 65)
        print(f"{item['label']}: {question}")
        print(f"Section 7.1 similarity: {target_score:.4f}")

        target_rank = None

        for rank, point in enumerate(results, start=1):
            payload = point.payload or {}
            section_id = payload.get("section_id", "")

            if section_id == TARGET_SECTION_ID:
                target_rank = rank

            print(
                f"Rank {rank}: Section {section_id} | "
                f"Score: {point.score:.4f}"
            )

            print(f"  Title: {payload.get('section_title', '')}")

        if target_rank is None:
            print(f"Section {TARGET_SECTION_ID} rank: outside top {TOP_K}")
        else:
            print(f"Section {TARGET_SECTION_ID} rank: {target_rank}")


if __name__ == "__main__":
    main()
