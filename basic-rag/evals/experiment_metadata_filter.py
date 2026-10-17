
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from basic_rag.config import COLLECTION_NAME, QDRANT_URL, TOP_K
from basic_rag.embedder import generate_embedding


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

    client = QdrantClient(url=QDRANT_URL)

    try:
        # 1. Normal vector search
        normal_results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=TOP_K,
            with_payload=True,
        ).points

        print_results("Normal vector search", normal_results)

        # 2. Vector search restricted to section 4.1
        filtered_results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="section_id",
                        match=MatchValue(value="4.1"),
                    )
                ]
            ),
            limit=TOP_K,
            with_payload=True,
        ).points

        print_results("Filtered vector search: section 4.1",
                      filtered_results)

    finally:
        client.close()


if __name__ == "__main__":
    main()
