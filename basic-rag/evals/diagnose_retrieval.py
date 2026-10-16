
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import COLLECTION_NAME
from qdrant_client import QdrantClient, models


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

TOP_K = 5
TARGET_SECTION_ID = "7.1"


def get_target_section(client):
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
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = sum(a * a for a in vector_a) ** 0.5
    norm_b = sum(b * b for b in vector_b) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def main():
    client = QdrantClient(url="http://localhost:6333")

    print("Connected to Qdrant")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Retrieving top {TOP_K} chunks per question")

    target_point = get_target_section(client)
    target_vector = target_point.vector

    # Handle named vectors if the collection uses them.
    if isinstance(target_vector, dict):
        target_vector = target_vector.get("")

    if target_vector is None:
        raise RuntimeError("Could not read the stored Section 7.1 vector.")

    for item in QUESTIONS:
        question = item["text"]
        question_embedding = generate_embedding(question)

        target_score = cosine_similarity(
            question_embedding,
            target_vector,
        )

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=question_embedding,
            limit=TOP_K,
            with_payload=True,
        ).points

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
