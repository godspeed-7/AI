"""The embeddings model and the Qdrant connection, shared by ingestion
and querying.

In:  settings from config.py (EMBEDDING_MODEL, the nomic prefixes,
     QDRANT_URL, COLLECTION_NAME).
Out: get_embeddings() -> the embeddings model (with nomic's prefixes);
     get_vector_store() -> a QdrantVectorStore on the existing
     collection, ready to search.

Strategy: both sides get the model from get_embeddings(), so chunks and
questions are always embedded by the same model (otherwise their
vectors can't be compared).

Caveats:
- get_vector_store() only connects; ingest.py creates the collection.
  Run ingest.py first, or it raises an error.
- Changing a prefix changes every vector: re-run ingest.py.
"""

from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import (
    COLLECTION_NAME,
    EMBED_DOCUMENT_PREFIX,
    EMBED_QUERY_PREFIX,
    EMBEDDING_MODEL,
    QDRANT_URL,
)


class NomicEmbeddings(OllamaEmbeddings):
    """OllamaEmbeddings that adds nomic's task prefixes: chunks get
    "search_document: ", questions get "search_query: ".

    A subclass (like JS `class extends`): only these two methods change;
    everything else (batching, the Ollama call) is inherited.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents(
            [EMBED_DOCUMENT_PREFIX + text for text in texts]
        )

    def embed_query(self, text: str) -> list[float]:
        # OllamaEmbeddings.embed_query just calls self.embed_documents,
        # which would now add the document prefix too. So call the
        # parent's embed_documents directly, with the query prefix only.
        return super().embed_documents([EMBED_QUERY_PREFIX + text])[0]


def get_embeddings() -> NomicEmbeddings:
    """Return the embeddings model used for chunks and questions."""
    return NomicEmbeddings(model=EMBEDDING_MODEL)


def get_vector_store() -> QdrantVectorStore:
    """Connect to the collection that ingest.py created."""
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        collection_name=COLLECTION_NAME,
        url=QDRANT_URL,
    )
