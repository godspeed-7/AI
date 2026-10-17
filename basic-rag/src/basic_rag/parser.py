"""Ingestion step 1: load documents from disk.

Only plain-text files are supported for now. Another format (PDF, DOCX)
would need its own loader that returns the same thing: one string with
the whole document.
"""

from pathlib import Path

from basic_rag.config import POLICIES_DIR


def load_document(file_path: str | Path) -> str:
    """Read a UTF-8 text file and return its full contents.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    return path.read_text(encoding="utf-8")


def list_documents(folder: str | Path = POLICIES_DIR) -> list[Path]:
    """Return every .txt file in the folder, sorted by name.

    Sorting keeps the ingestion order the same on every run.
    """
    return sorted(Path(folder).glob("*.txt"))


# Run this file directly to check that the policy documents load:
#   uv run python src/basic_rag/parser.py
if __name__ == "__main__":
    for document in list_documents():
        text = load_document(document)
        print(f"{document.name:34} {len(text):6} characters")
