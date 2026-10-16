from pathlib import Path


def load_document(file_path: str) -> str:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    return path.read_text(encoding="utf-8")


if __name__ == "__main__":
    text = load_document("documents/hr_leave_policy.txt")
    print(f"Characters loaded: {len(text)}")
    print(text[:500])
