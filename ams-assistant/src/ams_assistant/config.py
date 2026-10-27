"""Shared settings for ingestion and querying.

Every path (and later every URL, model name, and size) lives here, so
changing a setting means editing one line. Import what you need, e.g.
`from ams_assistant.config import POLICIES_DIR`.
"""

from pathlib import Path


# --- Paths -----------------------------------------------------------
# Anchored to the project root (two folders up from this file), so
# scripts work no matter which directory you run them from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The data lives next to this project in AI-demos/ams-data/, shared
# with basic-rag so both are measured on the same questions.
DATA_ROOT = PROJECT_ROOT.parent / "ams-data"
# Every .txt file in this folder is ingested as one document.
POLICIES_DIR = DATA_ROOT / "policies"
# The questions both projects are scored on (evals/).
EVALUATION_FILE = DATA_ROOT / "evaluation_questions.csv"


# --- Models (served by Ollama on localhost:11434) -------------------
# Embeds chunks and questions; 768 numbers per text. Same model as
# basic-rag.
EMBEDDING_MODEL = "nomic-embed-text"
# nomic was trained with a task prefix in front of every text: chunks
# and questions get different ones. OllamaEmbeddings doesn't add them,
# so vector_store.py does.
EMBED_DOCUMENT_PREFIX = "search_document: "
EMBED_QUERY_PREFIX = "search_query: "
# Writes the answers; same model and temperature as basic-rag.
LLM_MODEL = "gemma3:4b"
# 0 = always pick the most likely next word, so answers are repeatable.
TEMPERATURE = 0


# --- Qdrant ----------------------------------------------------------
QDRANT_URL = "http://localhost:6333"
# Not basic-rag's "ams_policies": both projects share one Qdrant server,
# and ingestion deletes and recreates its collection.
COLLECTION_NAME = "ams_policies_langchain"


# --- Retrieval -------------------------------------------------------
# Chunks returned per question; same as basic-rag.
TOP_K = 3
