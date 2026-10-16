
from qdrant_client import QdrantClient, models


COLLECTION_NAME = "hr_leave_policy"
VECTOR_SIZE = 384


def create_vector_store():
    client = QdrantClient(url="http://localhost:6333")

    collections = client.get_collections().collections
    collection_names = [
        collection.name for collection in collections
    ]

    # Recreate the collection to prevent stale points from
    # previous ingestion runs.
    if COLLECTION_NAME in collection_names:
        client.delete_collection(
            collection_name=COLLECTION_NAME
        )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )

    return client


def insert_chunks(client, embedded_chunks):
    points = []

    for chunk_id, chunk in enumerate(embedded_chunks):
        points.append(
            models.PointStruct(
                id=chunk_id,
                vector=chunk["embedding"],
                payload={
                    "text": chunk["text"],
                    "section": chunk["section"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "parent_section": chunk["parent_section"],
                    "chunk_index": chunk["chunk_index"],
                },
            )
        )

    if points:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )
