"""The embeddings model and the Qdrant connection, shared by ingestion
and querying.

In:  settings from config.py (EMBEDDING_MODEL, QDRANT_URL,
     COLLECTION_NAME).
Out: get_embeddings() -> the OllamaEmbeddings model;
     get_vector_store() -> a QdrantVectorStore on the existing
     collection, ready to search.

Strategy: both sides get the model from get_embeddings(), so chunks and
questions are always embedded by the same model (otherwise their
vectors can't be compared).

Caveats:
- get_vector_store() only connects; ingest.py creates the collection.
  Run ingest.py first, or it raises an error.
"""

from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import COLLECTION_NAME, EMBEDDING_MODEL, QDRANT_URL


def get_embeddings() -> OllamaEmbeddings:
    """Return the embeddings model used for chunks and questions."""
    return OllamaEmbeddings(model=EMBEDDING_MODEL)


def get_vector_store() -> QdrantVectorStore:
    """Connect to the collection that ingest.py created."""
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embeddings(),
        collection_name=COLLECTION_NAME,
        url=QDRANT_URL,
    )
