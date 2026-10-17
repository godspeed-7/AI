"""Ingestion pipeline: turn the policy document into searchable vectors.

Run from the basic-rag/ folder:
    uv run python ingest.py

Steps:
    1. Load    read documents/hr_leave_policy.txt         (parser.py)
    2. Chunk   split it into section-aware chunks          (chunker.py)
    3. Embed   turn each chunk into a 384-number vector    (embedder.py)
    4. Reset   connect to Qdrant and recreate the collection
    5. Store   save the chunks with their vectors          (vector_store.py)

WARNING: step 4 deletes everything in the collection before storing
the new chunks. Re-run this script whenever the document, the chunking
settings, or the embedding model change.

Needs Ollama (embeddings) and Qdrant running; see README.md.
"""

import time

from basic_rag.config import COLLECTION_NAME, DOCUMENT_PATH
from basic_rag.parser import load_document
from basic_rag.chunker import chunk_text
from basic_rag.embedder import embed_chunks
from basic_rag.vector_store import (
    get_client,
    insert_chunks,
    recreate_collection,
)
from basic_rag.logger import info, progress, success, heading, timing


def main():
    """Run all five ingestion steps and print a summary with timings."""
    start_time = time.perf_counter()

    heading("HR POLICY RAG INGESTION")

    # Step 1: Load document
    progress("[1/5] Loading HR policy document...")
    step_start = time.perf_counter()

    text = load_document(DOCUMENT_PATH)

    success(f"Loaded {len(text)} characters")
    timing("Document loading", time.perf_counter() - step_start)

    # Step 2: Chunk document
    progress("\n[2/5] Splitting document into chunks...")
    step_start = time.perf_counter()

    chunks = chunk_text(text)

    success(f"Created {len(chunks)} chunks")
    timing("Chunking", time.perf_counter() - step_start)

    # Step 3: Generate embeddings
    progress("\n[3/5] Generating embeddings using Ollama...")
    info(f"Processing {len(chunks)} chunks. Please wait...")

    step_start = time.perf_counter()

    embedded_chunks = embed_chunks(chunks)

    success(f"Generated {len(embedded_chunks)} embeddings")
    timing("Embedding generation", time.perf_counter() - step_start)

    # Step 4: Connect to Qdrant and reset the collection
    progress("\n[4/5] Connecting to Qdrant and recreating collection...")
    step_start = time.perf_counter()

    client = get_client()
    recreate_collection(client)

    success(f"Collection '{COLLECTION_NAME}' recreated")
    timing("Qdrant setup", time.perf_counter() - step_start)

    # Step 5: Store embeddings
    progress("\n[5/5] Storing embeddings in Qdrant...")
    step_start = time.perf_counter()

    insert_chunks(client, embedded_chunks, source=DOCUMENT_PATH.name)

    # Count what Qdrant actually stored; it should equal the chunk count.
    count = client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count

    success(f"Ingestion completed. Points in Qdrant: {count}")
    timing("Storage", time.perf_counter() - step_start)

    # Final summary
    total_time = time.perf_counter() - start_time

    heading("INGESTION SUMMARY")
    print(f"Characters loaded : {len(text)}")
    print(f"Chunks created    : {len(chunks)}")
    print(f"Chunks embedded   : {len(embedded_chunks)}")
    print(f"Points in Qdrant  : {count}")
    timing("Total ingestion time", total_time)


if __name__ == "__main__":
    main()
