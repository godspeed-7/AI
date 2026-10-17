"""Shared settings for ingestion, querying, and evaluation."""

from pathlib import Path


# Paths are anchored to the project root, so scripts work from any
# working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = PROJECT_ROOT / "documents" / "hr_leave_policy.txt"
EVALUATION_FILE = PROJECT_ROOT / "documents" / "evaluation_questions.csv"
EVALS_DIR = PROJECT_ROOT / "evals"

# Qdrant
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "hr_leave_policy"
# Must match the output size of EMBEDDING_MODEL.
VECTOR_SIZE = 384

# Ollama
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embed"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

# Models
EMBEDDING_MODEL = "all-minilm"
LLM_MODEL = "gemma3:4b"
# Kept separate from LLM_MODEL so the judge can be changed on its own.
JUDGE_MODEL = "gemma3:4b"
RERANKER_MODEL = "BAAI/bge-reranker-base"
TEMPERATURE = 0

# Chunking
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# Retrieval
TOP_K = 3
CANDIDATE_K = 20
RRF_K = 60
