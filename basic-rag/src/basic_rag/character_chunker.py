"""Simple fixed-size chunker (not used by the pipeline).

In:  a text string.
Out: a list of plain-string chunks.

Strategy: cut the text every `chunk_size - overlap` characters,
ignoring headings, sentences, and words. Kept as a baseline, e.g. to
measure how much section-aware chunking (chunker.py) actually helps.

Caveats:
- Returns strings, not chunk dicts with section metadata, so
  embedder.py and vector_store.py can't use it without adapting it.
"""


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[str]:
    """Split text into fixed-size, overlapping character windows.

    With chunk_size=500 and overlap=100, chunks start at characters
    0, 400, 800, ... so each chunk repeats the last 100 characters of
    the previous one. Cuts can fall in the middle of a word.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size")

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        # Move forward by less than a full chunk to create the overlap.
        start += chunk_size - overlap

    return chunks
