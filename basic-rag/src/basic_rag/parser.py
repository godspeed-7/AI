"""Ingestion step 1: load a document from disk.

Only plain-text files are supported for now. Another format (PDF, DOCX)
would need its own loader that returns the same thing: one string with
the whole document.
"""

from pathlib import Path

from basic_rag.config import DOCUMENT_PATH


def load_document(file_path: str | Path) -> str:
    """Read a UTF-8 text file and return its full contents.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    return path.read_text(encoding="utf-8")


# Run this file directly to check that the policy document loads:
#   uv run python src/basic_rag/parser.py
if __name__ == "__main__":
    text = load_document(DOCUMENT_PATH)
    print(f"Characters loaded: {len(text)}")
    print(text[:500])
