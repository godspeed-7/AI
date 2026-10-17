from pathlib import Path

from basic_rag.config import DOCUMENT_PATH


def load_document(file_path: str | Path) -> str:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    text = load_document(DOCUMENT_PATH)
    print(f"Characters loaded: {len(text)}")
    print(text[:500])
