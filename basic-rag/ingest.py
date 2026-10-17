"""Ingestion pipeline: turn the policy documents into searchable vectors.

Run from the basic-rag/ folder:
    uv run python ingest.py

Steps:
    1. Load    read every .txt file in documents/policies/  (parser.py)
    2. Chunk   split each one into section-aware chunks     (chunker.py)
    3. Embed   turn each chunk into a 384-number vector     (embedder.py)
    4. Reset   connect to Qdrant and recreate the collection
    5. Store   save each document's chunks with its file name
               as the source                               (vector_store.py)

WARNING: step 4 deletes everything in the collection before storing
the new chunks. Re-run this script whenever a document, the chunking
settings, or the embedding model change.

Needs Ollama (embeddings) and Qdrant running; see README.md.
"""

import time

from basic_rag.config import COLLECTION_NAME, POLICIES_DIR
from basic_rag.parser import list_documents, load_document
from basic_rag.chunker import chunk_text
from basic_rag.embedder import embed_chunks
from basic_rag.vector_store import (
    get_client,
    insert_chunks,
    recreate_collection,
)
from basic_rag.logger import (
    error,
    info,
    progress,
    success,
    heading,
    timing,
)


def main():
    """Run all five ingestion steps and print a summary with timings."""
    start_time = time.perf_counter()

    heading("AMS POLICY RAG INGESTION")

    # Step 1: Load documents
    progress(f"[1/5] Loading documents from {POLICIES_DIR}...")
    step_start = time.perf_counter()

    documents = list_documents(POLICIES_DIR)

    if not documents:
        error(f"No .txt documents found in {POLICIES_DIR}")
        return

    # File name -> full text. The file name becomes each chunk's source.
    texts = {path.name: load_document(path) for path in documents}
    total_characters = sum(len(text) for text in texts.values())

    success(
        f"Loaded {len(texts)} documents ({total_characters} characters)"
    )
    timing("Document loading", time.perf_counter() - step_start)

    # Step 2: Chunk each document separately, so a chunk never mixes
    # text from two documents.
    progress("\n[2/5] Splitting documents into chunks...")
    step_start = time.perf_counter()

    chunks_by_document = {
        name: chunk_text(text) for name, text in texts.items()
    }
    total_chunks = sum(len(chunks) for chunks in chunks_by_document.values())

    for name, chunks in chunks_by_document.items():
        info(f"{name}: {len(chunks)} chunks")
    success(f"Created {total_chunks} chunks")
    timing("Chunking", time.perf_counter() - step_start)

    # Step 3: Generate embeddings
    progress("\n[3/5] Generating embeddings using Ollama...")
    info(f"Processing {total_chunks} chunks. Please wait...")

    step_start = time.perf_counter()

    embedded_by_document = {
        name: embed_chunks(chunks)
        for name, chunks in chunks_by_document.items()
    }
    total_embedded = sum(
        len(chunks) for chunks in embedded_by_document.values()
    )

    success(f"Generated {total_embedded} embeddings")
    timing("Embedding generation", time.perf_counter() - step_start)

    # Step 4: Connect to Qdrant and reset the collection
    progress("\n[4/5] Connecting to Qdrant and recreating collection...")
    step_start = time.perf_counter()

    client = get_client()
    recreate_collection(client)

    success(f"Collection '{COLLECTION_NAME}' recreated")
    timing("Qdrant setup", time.perf_counter() - step_start)

    # Step 5: Store embeddings, one document at a time so each chunk is
    # saved with the file name it came from.
    progress("\n[5/5] Storing embeddings in Qdrant...")
    step_start = time.perf_counter()

    for name, embedded_chunks in embedded_by_document.items():
        insert_chunks(client, embedded_chunks, source=name)

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
    print(f"Documents loaded  : {len(texts)}")
    print(f"Characters loaded : {total_characters}")
    print(f"Chunks created    : {total_chunks}")
    print(f"Chunks embedded   : {total_embedded}")
    print(f"Points in Qdrant  : {count}")
    timing("Total ingestion time", total_time)


if __name__ == "__main__":
    main()
