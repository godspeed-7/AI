"""Simple fixed-size chunker (not used by the pipeline yet).

The most basic chunking strategy: cut the text every
`chunk_size - overlap` characters, ignoring headings, sentences, and
words. Kept as an alternative to chunker.py, e.g. to measure how much
section-aware chunking actually helps.

Note: this returns plain strings, while chunker.py returns dicts with
section metadata. To use it in the pipeline, embedder.embed_chunks and
vector_store.insert_chunks would need chunks in the dict format.
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
