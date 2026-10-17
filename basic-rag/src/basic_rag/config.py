"""Shared settings for ingestion, querying, and evaluation.

Every URL, model name, size, and path lives here, so changing a setting
means editing one line instead of hunting through many files. Import
what you need, e.g. `from basic_rag.config import TOP_K`.
"""

from pathlib import Path


# --- Paths -----------------------------------------------------------
# Anchored to the project root (two folders up from this file), so
# scripts work no matter which directory you run them from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = PROJECT_ROOT / "documents" / "hr_leave_policy.txt"
EVALUATION_FILE = PROJECT_ROOT / "documents" / "evaluation_questions.csv"
EVALS_DIR = PROJECT_ROOT / "evals"

# --- Qdrant (vector database) ------------------------------------------
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "hr_leave_policy"
# Length of each embedding vector. Must match the output size of
# EMBEDDING_MODEL; if you change the model, change this and re-ingest.
VECTOR_SIZE = 384

# --- Ollama (local model server) ---------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

# --- Models ------------------------------------------------------------
# Turns text into vectors. Documents and questions must use the same one.
EMBEDDING_MODEL = "all-minilm"
# Writes the answers (and rewrites/expands queries in the evals).
LLM_MODEL = "gemma3:4b"
# Grades answers in evals/evaluate_answers.py. Kept separate from
# LLM_MODEL so the judge can be changed on its own.
JUDGE_MODEL = "gemma3:4b"
# Cross-encoder used by the reranking experiment (Hugging Face model).
RERANKER_MODEL = "BAAI/bge-reranker-base"
# 0 = always pick the most likely next word, so answers are repeatable.
TEMPERATURE = 0

# --- Chunking (sizes are in characters, not tokens) ---------------------
# Longest chunk the chunker will produce.
CHUNK_SIZE = 500
# Characters repeated at the start of the next chunk, so a sentence cut
# at a chunk boundary still appears whole in one of the two chunks.
CHUNK_OVERLAP = 100

# --- Retrieval -----------------------------------------------------------
# Number of chunks given to the LLM as context.
TOP_K = 3
# Wider first pass for reranking/hybrid: fetch this many, then narrow
# down to TOP_K.
CANDIDATE_K = 20
# Constant in Reciprocal Rank Fusion (hybrid search). 60 is the usual
# default; larger values flatten the difference between ranks.
RRF_K = 60
