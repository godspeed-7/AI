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


# --- Models (served by Ollama on localhost:11434) -------------------
# Embeds chunks and questions; 768 numbers per text. Same model as
# basic-rag, but without nomic's "search_document: " /
# "search_query: " prefixes (OllamaEmbeddings doesn't add them).
EMBEDDING_MODEL = "nomic-embed-text"
# Writes the answers; same model and temperature as basic-rag.
LLM_MODEL = "gemma3:4b"
# 0 = always pick the most likely next word, so answers are repeatable.
TEMPERATURE = 0


# --- Qdrant ----------------------------------------------------------
QDRANT_URL = "http://localhost:6333"
# Not basic-rag's "ams_policies": both projects share one Qdrant server,
# and ingestion deletes and recreates its collection.
COLLECTION_NAME = "ams_policies_langchain"


# --- Chunking (sizes are in characters, not tokens) -----------------
# Same values as basic-rag, so the two pipelines are compared fairly.
# Longest chunk the splitter will produce.
CHUNK_SIZE = 500
# Characters repeated at the start of the next chunk. 0 for now, to
# match basic-rag; unlike basic-rag's chunker, this splitter can cut
# mid-sentence, so overlap is worth trying later.
CHUNK_OVERLAP = 0


# --- Retrieval -------------------------------------------------------
# Chunks returned per question; same as basic-rag.
TOP_K = 3
