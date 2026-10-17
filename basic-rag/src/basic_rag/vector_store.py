
import uuid

from qdrant_client import QdrantClient, models

from basic_rag.config import (
    COLLECTION_NAME,
    QDRANT_URL,
    TOP_K,
    VECTOR_SIZE,
)


def get_client() -> QdrantClient:
    """Connect to Qdrant. Safe to call anywhere; it changes nothing."""
    return QdrantClient(url=QDRANT_URL)


def recreate_collection(client: QdrantClient) -> None:
    """Delete and recreate the collection.

    This destroys every stored point. Only ingestion should call it.
    """
    # Recreate the collection to prevent stale points from
    # previous ingestion runs.
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(collection_name=COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )


def make_point_id(
    source: str,
    section_id: str,
    chunk_index: int,
) -> str:
    """Build a deterministic UUID from where the chunk came from.

    The same document, section, and chunk always get the same ID, and
    chunks from different documents never collide.
    """
    key = f"{source}#{section_id}#{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def insert_chunks(
    client: QdrantClient,
    embedded_chunks: list[dict],
    source: str,
) -> None:
    points = []
    seen_ids = set()

    for chunk in embedded_chunks:
        point_id = make_point_id(
            source, chunk["section_id"], chunk["chunk_index"]
        )

        # Two chunks with the same ID would silently overwrite each
        # other, e.g. if a document repeats a section number.
        if point_id in seen_ids:
            raise ValueError(
                f"Duplicate chunk ID in {source}: section "
                f"{chunk['section_id']!r}, chunk {chunk['chunk_index']}"
            )
        seen_ids.add(point_id)

        points.append(
            models.PointStruct(
                id=point_id,
                vector=chunk["embedding"],
                payload={
                    "text": chunk["text"],
                    "source": source,
                    "section": chunk["section"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "parent_section": chunk["parent_section"],
                    "chunk_index": chunk["chunk_index"],
                    "document_type": "hr_policy",
                },
            )
        )

    if points:
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )


def search(
    client: QdrantClient,
    query_vector: list[float],
    limit: int = TOP_K,
    query_filter: models.Filter | None = None,
) -> list:
    """Return the chunks nearest to the query vector, best first."""
    return client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    ).points
