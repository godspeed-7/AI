"""Ingestion pipeline (LangChain version): policies -> searchable vectors.

Steps:
    1. Load            read every .txt file in ams-data/policies/ as a
                       Document
    2. Chunk           split each Document into chunks of up to
                       CHUNK_SIZE characters (RecursiveCharacterTextSplitter)
    3. Embed + store   recreate the Qdrant collection, embed every chunk
                       with EMBEDDING_MODEL, and store it
                       (QdrantVectorStore.from_documents)

Strategy: same steps as basic-rag/ingest.py, but every step passes
LangChain Document objects (text + metadata) instead of plain strings
and dicts.

Caveats:
- Each file type has its own loader in LOADERS; only .txt exists so far
  (plain pathlib, no LangChain loader). A file with no loader stops
  ingestion with an error instead of being skipped silently.
- The splitter doesn't know about numbered sections (unlike
  basic-rag's chunker): a chunk can hold the end of one section and the
  start of the next, and chunks carry only the "source" metadata.
- Chunks are embedded as plain text: no nomic task prefix and no
  document/section header in front (both of which basic-rag adds).
- Step 3 deletes everything in COLLECTION_NAME before storing. Re-run
  this script whenever a document, the chunking, or the model change.
- Qdrant stores each chunk as {"page_content": ..., "metadata": {...}},
  so filters use "metadata.source" (basic-rag's payload is flat).
- Needs Ollama (with EMBEDDING_MODEL pulled) and Qdrant running.
"""

from collections import Counter
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ams_assistant.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    POLICIES_DIR,
    QDRANT_URL,
)
from ams_assistant.vector_store import get_embeddings


def load_text_file(path: Path) -> list[Document]:
    """Load a UTF-8 text file as one Document.

    page_content holds the full text; metadata["source"] holds the file
    name, so every chunk made from it later knows where it came from.
    """
    return [
        Document(
            page_content=path.read_text(encoding="utf-8"),
            metadata={"source": path.name},
        )
    ]


# File extension -> loader. Every loader returns list[Document], since
# some formats give several (a PDF loader gives one per page). To
# support a new format, add one line here (and its package).
LOADERS = {
    ".txt": load_text_file,
}


def load_documents(folder: Path = POLICIES_DIR) -> list[Document]:
    """Load every file in the folder, sorted by name, with its loader.

    Hidden files (.DS_Store, ...) are skipped. Raises ValueError for a
    file type with no loader.
    """
    documents = []

    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue

        loader = LOADERS.get(path.suffix.lower())

        if loader is None:
            supported = ", ".join(LOADERS)
            raise ValueError(
                f"No loader for {path.name}; supported: {supported}"
            )

        # extend adds every Document from the list (like JS push(...docs)).
        documents.extend(loader(path))

    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Split Documents into chunks; each chunk copies its metadata.

    Tries to cut at blank lines first, then line breaks, then spaces,
    then anywhere, until every chunk fits in CHUNK_SIZE characters.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_documents(documents)


def main():
    """Run the three ingestion steps and print what they made."""
    # Step 1: Load
    documents = load_documents()
    total_characters = sum(len(doc.page_content) for doc in documents)
    print(f"Loaded {len(documents)} documents ({total_characters} characters)")

    # Step 2: Chunk
    chunks = split_documents(documents)
    print(f"\nCreated {len(chunks)} chunks")

    # Chunks per document; Counter counts how often each source appears.
    for source, count in Counter(c.metadata["source"] for c in chunks).items():
        print(f"  {source}: {count} chunks")

    # Step 3: Embed + store. from_documents does it all in one call:
    # deletes the old collection (force_recreate=True), creates a new one,
    # calls embeddings.embed_documents on every chunk (in batches), and
    # stores each vector with its chunk's text and metadata.
    print(f"\nEmbedding and storing {len(chunks)} chunks "
          f"in '{COLLECTION_NAME}'...")
    embeddings = get_embeddings()
    vector_store = QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=QDRANT_URL,
        collection_name=COLLECTION_NAME,
        force_recreate=True,
    )

    # Count what Qdrant actually stored; it should equal the chunk count.
    count = vector_store.client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count
    print(f"Points in Qdrant: {count}")


if __name__ == "__main__":
    main()
