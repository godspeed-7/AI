"""Ingestion step 1: find and load the documents from disk.

In:  a folder (list_documents, default POLICIES_DIR) or one file path
     (load_document).
Out: the folder's .txt files sorted by name, or one file's full text
     as a single string.

Caveats:
- Only plain-text (.txt) files are supported. Another format (PDF,
  DOCX) would need its own loader that returns the same: one string.
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
