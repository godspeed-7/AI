
import time

from basic_rag.config import COLLECTION_NAME, DOCUMENT_PATH
from basic_rag.parser import load_document
from basic_rag.chunker import chunk_text
from basic_rag.embedder import embed_chunks
from basic_rag.vector_store import create_vector_store, insert_chunks
from basic_rag.logger import info, progress, success, heading, timing


def main():
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

    # Step 4: Connect to Qdrant
    progress("\n[4/5] Connecting to Qdrant...")
    step_start = time.perf_counter()

    client = create_vector_store()

    success("Connected to Qdrant")
    timing("Qdrant connection", time.perf_counter() - step_start)

    # Step 5: Store embeddings
    progress("\n[5/5] Storing embeddings in Qdrant...")
    step_start = time.perf_counter()

    insert_chunks(client, embedded_chunks)

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
