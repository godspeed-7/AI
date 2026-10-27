"""Ingestion pipeline (LangChain version): policies -> searchable vectors.

Steps (built one at a time):
    1. Load    read every .txt file in ams-data/policies/ as a Document
    2. Chunk   (next)
    3. Embed   (next)
    4. Store   (next)

Strategy: same steps as basic-rag/ingest.py, but every step passes
LangChain Document objects (text + metadata) instead of plain strings
and dicts.

Caveats:
- Each file type has its own loader in LOADERS; only .txt exists so far
  (plain pathlib, no LangChain loader). A file with no loader stops
  ingestion with an error instead of being skipped silently.
"""

from pathlib import Path

from langchain_core.documents import Document

from ams_assistant.config import POLICIES_DIR


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


def main():
    """Run the ingestion steps built so far and print what they made."""
    # Step 1: Load
    documents = load_documents()
    total_characters = sum(len(doc.page_content) for doc in documents)
    print(f"Loaded {len(documents)} documents ({total_characters} characters)")

    # One example, to see what a Document looks like.
    example = documents[0]
    print(f"\nExample: {example.metadata}")
    print(example.page_content[:200])


if __name__ == "__main__":
    main()
