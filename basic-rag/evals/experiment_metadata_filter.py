
from qdrant_client.models import Filter, FieldCondition, MatchValue

from basic_rag.config import TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search


def print_results(title, points):
    print(f"\n--- {title} ---")

    if not points:
        print("No matching chunks found.")
        return

    for rank, point in enumerate(points, start=1):
        payload = point.payload or {}

        print(f"\nRank: {rank}")
        print(f"Section: {payload.get('section_id', '')}")
        print(f"Title: {payload.get('section_title', '')}")
        print(f"Text: {payload.get('text', '')[:200]}")


def main():
    question = (
        "How many unused annual-leave days "
        "can normally carry over?"
    )

    embedding = generate_embedding(question)

    client = get_client()

    try:
        # 1. Normal vector search
        normal_results = search(client, embedding, limit=TOP_K)

        print_results("Normal vector search", normal_results)

        # 2. Vector search restricted to section 4.1
        filtered_results = search(
            client,
            embedding,
            limit=TOP_K,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="section_id",
                        match=MatchValue(value="4.1"),
                    )
                ]
            ),
        )

        print_results("Filtered vector search: section 4.1",
                      filtered_results)

    finally:
        client.close()


if __name__ == "__main__":
    main()
