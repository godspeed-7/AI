
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import COLLECTION_NAME
from qdrant_client import QdrantClient, models


QUESTION = "Does the policy specify a fixed number of parental-leave days?"


def diagnose_retrieval(client):
    print("\n--- Retrieval diagnostic ---")
    print(f"Question: {QUESTION}")

    question_embedding = generate_embedding(QUESTION)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=question_embedding,
        limit=5,
        with_payload=True,
    ).points

    print(f"\nRetrieved {len(results)} chunks")

    for rank, point in enumerate(results, start=1):
        payload = point.payload

        print(f"\n--- Rank {rank} ---")
        print(f"Section ID: {payload.get('section_id')}")
        print(f"Section: {payload.get('section')}")
        print(f"Similarity score: {point.score:.4f}")
        print(f"Text: {payload.get('text')}")


def check_stored_embedding(client):
    print("\n--- Checking stored embedding for Section 7.1 ---")

    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="section_id",
                    match=models.MatchValue(value="7.1"),
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=True,
    )

    if not points:
        print("Section 7.1 was not found in Qdrant.")
        return

    point = points[0]
    payload = point.payload

    embedding_text = (
        f"Section: {payload['section_id']} "
        f"{payload['section_title']}\n"
        f"Parent section: {payload['parent_section']}\n\n"
        f"{payload['text']}"
    )

    fresh_embedding = generate_embedding(embedding_text)
    stored_embedding = point.vector

    # Qdrant may return a named-vector dictionary rather than a list.
    if isinstance(stored_embedding, dict):
        stored_embedding = stored_embedding.get("")

    if stored_embedding is None:
        print("Could not read the stored vector.")
        return

    if len(stored_embedding) != len(fresh_embedding):
        print("Vector dimensions do not match!")
        print(f"Stored dimensions: {len(stored_embedding)}")
        print(f"Fresh dimensions: {len(fresh_embedding)}")
        return

    dot_product = sum(
        a * b for a, b in zip(stored_embedding, fresh_embedding)
    )
    stored_norm = sum(a * a for a in stored_embedding) ** 0.5
    fresh_norm = sum(b * b for b in fresh_embedding) ** 0.5

    if stored_norm == 0 or fresh_norm == 0:
        print("Cannot compare zero-length vectors.")
        return

    similarity = dot_product / (stored_norm * fresh_norm)

    print(f"Section: {payload['section_id']} - "
          f"{payload['section_title']}")
    print(f"Stored vector dimensions: {len(stored_embedding)}")
    print(f"Fresh vector dimensions: {len(fresh_embedding)}")
    print(f"Stored vs fresh cosine similarity: {similarity:.6f}")


def main():
    client = QdrantClient(url="http://localhost:6333")

    print("Connected to Qdrant")
    print(f"Collection: {COLLECTION_NAME}")

    diagnose_retrieval(client)
    check_stored_embedding(client)


if __name__ == "__main__":
    main()
