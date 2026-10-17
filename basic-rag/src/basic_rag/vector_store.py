"""Everything that talks to Qdrant, the vector database.

Ingestion step 4-5 and query step 2. Functions, from safe to dangerous:

    get_client()           connect; changes nothing, safe anywhere
    search()               find the chunks nearest to a query vector
    insert_chunks()        store embedded chunks (upsert)
    recreate_collection()  DELETE all chunks and start fresh;
                           only ingest.py should call this

Each stored item is a "point": an ID, a vector, and a payload (a dict
with the chunk text, the file it came from as `source`, the document's
title and version as `document_title`, and its section metadata).
"""

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

    # COSINE compares the direction of vectors, not their length,
    # which is the standard choice for text embeddings.
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
    # uuid5 hashes the key, so the same key always gives the same UUID
    # (unlike uuid4, which is random). Qdrant only accepts integers or
    # UUIDs as point IDs, so the readable key can't be used directly.
    key = f"{source}#{section_id}#{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def insert_chunks(
    client: QdrantClient,
    embedded_chunks: list[dict],
    source: str,
) -> None:
    """Store embedded chunks in Qdrant as points.

    `embedded_chunks` come from embedder.embed_chunks; `source` is the
    document's file name (e.g. "leave_policy_us.txt") and is saved in
    every payload. Raises ValueError if two chunks would share an ID.
    """
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

        # The payload is what comes back with search results; the
        # vector itself is only used for matching.
        points.append(
            models.PointStruct(
                id=point_id,
                vector=chunk["embedding"],
                payload={
                    "text": chunk["text"],
                    "source": source,
                    "document_title": chunk["document_title"],
                    "section": chunk["section"],
                    "section_id": chunk["section_id"],
                    "section_title": chunk["section_title"],
                    "parent_section": chunk["parent_section"],
                    "chunk_index": chunk["chunk_index"],
                    "document_type": "company_policy",
                },
            )
        )

    # Upsert = insert new IDs, overwrite existing ones. All points are
    # sent in one request.
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
    """Return the chunks nearest to the query vector, best first.

    Each result is a Qdrant point with `.payload` (chunk text and
    metadata) and `.score` (cosine similarity, higher = closer). Pass
    `query_filter` to restrict the search, e.g. to one document
    (`source`). Filtering on section_id alone matches that section
    number in every document that has it.
    """
    return client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    ).points
