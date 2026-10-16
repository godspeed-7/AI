import json
from urllib.request import Request, urlopen


OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBEDDING_MODEL = "all-minilm"


def generate_embedding(text: str) -> list[float]:
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

    return result["embeddings"][0]


def embed_chunks(chunks: list[dict]) -> list[dict]:
    embedded_chunks = []

    for chunk in chunks:
        # Add section context to improve semantic retrieval.
        embedding_text = (
            f"Section: {chunk['section_id']} {chunk['section_title']}\n"
            f"Parent section: {chunk['parent_section']}\n\n"
            f"{chunk['text']}"
        )

        embedding = generate_embedding(embedding_text)

        embedded_chunks.append({
            **chunk,
            "embedding": embedding,
        })

    return embedded_chunks
