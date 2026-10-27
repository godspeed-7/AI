"""Ingestion pipeline (LangChain version): policies -> searchable vectors.

Steps:
    1. Load            read every .txt file in ams-data/policies/ as a
                       Document
    2. Chunk           split each Document at blank lines: one chunk per
                       block (in these docs, one top-level section),
                       with the document title in front
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
- Chunking relies on these docs putting a blank line between
  sections. There is no size limit: a long block with no blank lines
  becomes one big chunk (today's largest is 1,491 characters).
- Each doc's title block and TRAINING NOTE become chunks too.
- Chunks carry "source" and "title" metadata, no section number.
- The "Document: <title>" line is part of the stored chunk text, so
  the LLM sees it too (basic-rag adds its header to the embedded text
  only). Embedding adds nomic's prefix (vector_store.py).
- Step 3 deletes everything in COLLECTION_NAME before storing. Re-run
  this script whenever a document, the chunking, or the model changes.
- Qdrant stores each chunk as {"page_content": ..., "metadata": {...}},
  so filters use "metadata.source" (basic-rag's payload is flat).
- Needs Ollama (with EMBEDDING_MODEL pulled) and Qdrant running.
"""

import re
from collections import Counter
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import COLLECTION_NAME, POLICIES_DIR, QDRANT_URL
from ams_assistant.vector_store import get_embeddings


def read_title(text: str) -> str:
    """Return the document title: the line just above the first line
    containing "Version:", or "" if there is none.

    Every AMS file starts like this:
        AMS
        EMPLOYEE LEAVE POLICY (INDIA)
        Policy ID: HR-LEAVE-IN-2026 | Version: 2.1 | ...
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for i, line in enumerate(lines[:10]):
        if "Version:" in line and i > 0:
            return lines[i - 1]

    return ""


def load_text_file(path: Path) -> list[Document]:
    """Load a UTF-8 text file as one Document.

    page_content holds the full text; metadata holds the file name
    ("source") and the title, so every chunk made from it later knows
    where it came from.
    """
    text = path.read_text(encoding="utf-8")
    return [
        Document(
            page_content=text,
            metadata={"source": path.name, "title": read_title(text)},
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
    """One chunk per blank-line block; in these docs, one top-level
    section each. Each chunk copies its document's metadata.

    Each chunk starts with a "Document: <title>" line. Most sections
    never name their document ("5. SICK LEAVE" doesn't say India), so
    without it an India and a US chunk can look alike to the search.

    Plain Python, not RecursiveCharacterTextSplitter: that splitter
    always merges small blocks up to its chunk_size, and here every
    section should stay a chunk of its own.
    """
    chunks = []

    for doc in documents:
        title = doc.metadata["title"]
        header = f"Document: {title}\n" if title else ""

        # \n\s*\n = a blank line (even one holding stray spaces).
        for block in re.split(r"\n\s*\n", doc.page_content):
            if block.strip():
                chunks.append(Document(
                    page_content=header + block.strip(),
                    metadata=dict(doc.metadata),
                ))

    return chunks


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
