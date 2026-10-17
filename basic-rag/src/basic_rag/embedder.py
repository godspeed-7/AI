"""Ingestion step 3 and query step 1: turn text into embedding vectors.

In:  chunk dicts from chunker.py (embed_chunks), or one question string
     (generate_embedding).
Out: the same chunk dicts with an "embedding" key added, or one vector
     (384 numbers for all-minilm) that captures the text's meaning.

Strategy: each chunk is embedded with its document title and section
heading in front, so the vector also reflects where the text comes
from. Questions are embedded as typed. Calls Ollama's /api/embed with
EMBEDDING_MODEL.

Caveats:
- Chunks and questions must use the same model, or their vectors can't
  be compared. A new model means updating VECTOR_SIZE and re-ingesting.
- One request per chunk: fine for hundreds of chunks, slow for
  thousands.
"""

import json
from urllib.request import Request, urlopen

from basic_rag.config import EMBEDDING_MODEL, OLLAMA_EMBED_URL


def generate_embedding(text: str) -> list[float]:
    """Return the embedding vector for one piece of text.

    Used for each chunk during ingestion and for the question at query
    time.
    """
    request_data = {
        "model": EMBEDDING_MODEL,
        "input": text,
    }

    request = Request(
        url=OLLAMA_EMBED_URL,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))

    # Ollama returns a list of embeddings (one per input); we sent one.
    return result["embeddings"][0]


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Embed every chunk and return copies with an "embedding" key added.

    Sends one request per chunk. Ollama's /api/embed also accepts a list
    of inputs, which would be faster for large documents.
    """
    embedded_chunks = []

    for chunk in chunks:
        # Add document and section context to improve retrieval.
        # A chunk like "Employees may carry over up to 5 days..." doesn't
        # say it's about annual leave in the India policy; its heading
        # and document title do. Only this embedding text gets the
        # prefix; the stored chunk text stays plain.
        embedding_text = (
            f"Document: {chunk['document_title']}\n"
            f"Section: {chunk['section_id']} {chunk['section_title']}\n"
            f"Parent section: {chunk['parent_section']}\n\n"
            f"{chunk['text']}"
        )

        embedding = generate_embedding(embedding_text)

        # {**chunk, ...} copies the dict (like JS spread) and adds a key.
        embedded_chunks.append({
            **chunk,
            "embedding": embedding,
        })

    return embedded_chunks
