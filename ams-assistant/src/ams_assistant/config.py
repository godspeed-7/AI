"""Shared settings for ingestion and querying.

Every path (and later every URL, model name, and size) lives here, so
changing a setting means editing one line. Import what you need, e.g.
`from ams_assistant.config import POLICIES_DIR`.
"""

from datetime import date
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
# The agent's test questions (evals/evaluate_agent.py): who asks, the
# question, the expected answer and the tools it must use.
AGENT_QUESTIONS_FILE = DATA_ROOT / "agent_questions.csv"
# Company facts as "term -> also add" rules (glossary.py), from the
# handbooks' own definitions. ingest.py adds them to chunks; re-run it
# after editing the file.
GLOSSARY_FILE = DATA_ROOT / "glossary.csv"
# The judge's instructions, shared so both projects grade answers the
# same way (basic-rag still has its own identical copy in judge.py).
JUDGE_PROMPT_FILE = DATA_ROOT / "judge_prompt.txt"
# Where the answer eval writes its per-question results.
EVALS_DIR = PROJECT_ROOT / "evals"
# The reranker's saved scores (reranker.py); not in git. Deleting it is
# always safe: scores are recomputed as needed.
RERANK_CACHE_FILE = PROJECT_ROOT / ".cache" / "rerank_scores.sqlite"
# Saved LLM replies (llm_cache.py): answers, judge grades, rewrites.
# Also safe to delete.
LLM_CACHE_FILE = PROJECT_ROOT / ".cache" / "llm_replies.sqlite"
# The HR records (employees, leave, expenses) as CSVs, shared in
# ams-data. build_hr_db.py copies them into HR_DB_FILE.
HR_DATA_DIR = DATA_ROOT / "db"
# The agent's HR database (hr_tools.py reads it); not in git. Safe to
# delete: re-run build_hr_db.py for a fresh copy of the CSVs.
HR_DB_FILE = PROJECT_ROOT / ".cache" / "hr.sqlite"
# The date the HR data describes (TODAY in ams-data/db/build_hr_data.py).
# The agent works with it, never the real clock: the tools count from
# it (e.g. time at AMS) and the model is told it.
TODAY = date(2026, 11, 16)


# --- Models (served by Ollama on localhost:11434) -------------------
# Embeds chunks and questions; 768 numbers per text. Same model as
# basic-rag.
EMBEDDING_MODEL = "nomic-embed-text"
# nomic was trained with a task prefix in front of every text: chunks
# and questions get different ones. OllamaEmbeddings doesn't add them,
# so vector_store.py does.
EMBED_DOCUMENT_PREFIX = "search_document: "
EMBED_QUERY_PREFIX = "search_query: "
# Writes the answers; same model and temperature as basic-rag. Also
# runs the experiments' LLM steps (query rewriting etc.), always on
# Ollama.
LLM_MODEL = "gemma3:4b"
# Where the answers are written: "ollama" + LLM_MODEL (this Mac), or a
# hosted model, e.g. "google" + "gemma-4-31b-it" (Run 2, 2026-11-07:
# does a bigger model answer better?). Providers as for the judge.
ANSWER_PROVIDER = "ollama"
ANSWER_MODEL = LLM_MODEL
# Grades answers in evals/evaluate_answers.py. Kept separate from
# LLM_MODEL so the judge can be changed on its own. Where it runs:
# "ollama" (this Mac), "google" (AI Studio free tier; needs
# GOOGLE_API_KEY) or "nvidia" (build.nvidia.com free tier; needs
# NVIDIA_API_KEY). On a 40-answer key (2026-11-06): Nemotron 3 Ultra
# (nvidia) 35/40, gemma-4-31b-it 30/36, gemma-4-26b-a4b-it 28/35,
# gemma3:12b 29/40, gemma3:4b 20/40. Gemma 4 26B is the judge: free,
# stable and a full run fits one sitting (NVIDIA's free quota runs
# out mid-run). Switch with e.g. "nvidia" +
# "nvidia/nemotron-3-ultra-550b-a55b", or "ollama" + "gemma3:12b".
JUDGE_PROVIDER = "google"
JUDGE_MODEL = "gemma-4-26b-a4b-it"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Google's free tier allows each Gemma 4 model 16,000 tokens a minute;
# one grade sends ~1,200 (at most ~1,500), so each model gets at most
# this many calls a minute.
GOOGLE_CALLS_PER_MINUTE = 6
# 0 = always pick the most likely next word, so answers are repeatable.
TEMPERATURE = 0
# The agent's model (agent_by_hand.py): picks the tools and writes the
# reply. Providers as for the judge. Local, so test runs have no daily
# limit and the judge keeps Google's quota; needs a model with tool
# support (gemma3 has none). On 2026-11-10 Google's Gemma 4 failed
# every call with tools (500) and Gemini's free limits were unclear;
# "google" + "gemini-3.5-flash-lite" passed a tool test (second
# opinion).
AGENT_PROVIDER = "ollama"
AGENT_MODEL = "qwen3:8b"
# qwen3 thinks before it replies. True prints the thinking in the log
# (~13 s a round); False skips it (~2 s). Both picked the right tool
# in a test. Ollama only.
AGENT_THINKING = True
# Model replies per question before the loop gives up.
AGENT_MAX_STEPS = 5
# The web app (app.py): True shows every step live under each question
# (model calls, thinking, tools, times); False shows only the answer.
SHOW_AGENT_STEPS = True


# --- Qdrant ----------------------------------------------------------
QDRANT_URL = "http://localhost:6333"
# Not basic-rag's "ams_policies": both projects share one Qdrant server,
# and ingestion deletes and recreates its collection.
COLLECTION_NAME = "ams_policies_langchain"


# --- Retrieval -------------------------------------------------------
# Chunks returned per question; same as basic-rag.
TOP_K = 3
# Query expansion (experiments/): LLM-written phrasings searched in
# addition to the original question; same as basic-rag.
NUM_ALTERNATIVES = 2
# Reranking (on or off: Pipeline.rerank in pipeline.py): vector search
# fetches CANDIDATE_K chunks, the cross-encoder re-scores them, and the
# best TOP_K are kept. The model comes from Hugging Face (cached after
# the first download).
# v2-m3 replaced basic-rag's bge-reranker-base: with 10 candidates it
# kept the right section in the top 3 more often (96.2% vs 95.4%),
# mostly on casual questions, at ~0.85 s vs ~0.25 s per question.
CANDIDATE_K = 10
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
# Contextual retrieval (experiments/): the LLM reads a whole handbook
# to write each chunk's context line. Ollama's default context window
# is a few thousand tokens; the Employee Handbook is about 14,000.
CONTEXT_NUM_CTX = 16384
# Its own collection, so the experiment never touches COLLECTION_NAME.
CONTEXTUAL_COLLECTION_NAME = "ams_policies_contextual"
# Glossary (experiments/): chunks with their "Glossary: ..." line, in
# their own collection for the same reason.
GLOSSARY_COLLECTION_NAME = "ams_policies_glossary"
# Hypothetical questions (experiments/): the LLM writes this many
# questions per chunk; each is stored as an extra point that leads
# back to its chunk.
NUM_HYPOTHETICAL_QUESTIONS = 3
HYPOTHETICAL_COLLECTION_NAME = "ams_policies_hypothetical"
