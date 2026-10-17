# Basic RAG: HR Leave Policy

A small Retrieval-Augmented Generation (RAG) project built from scratch in
Python, without LangChain or similar frameworks, so every step of the
pipeline stays visible. It answers questions about a fictional HR leave
policy using:

- **Ollama** for embeddings (`all-minilm`) and answer generation
  (`gemma3:4b`)
- **Qdrant** as the vector database

## Architecture

```text
INGESTION (ingest.py)

documents/hr_leave_policy.txt
        |
        v
  parser.py       load the text
        |
        v
  chunker.py      split by policy section, then into ~500-char chunks
        |         (35 chunks; each keeps section id, title, parent)
        v
  embedder.py     embed "section title + parent + chunk text"
        |         with all-minilm (384 dimensions)
        v
  vector_store.py recreate the collection, store chunks with
                  deterministic UUIDs and their source document


QUERY (query.py)

question -> embedder.py -> vector_store.search() top 3 chunks
                                   |
                                   v
                     prompts.build_prompt(question, chunks)
                                   |
                                   v
                     generator.py (gemma3:4b) -> answer
```

## Project layout

```text
basic-rag/
├── documents/
│   ├── hr_leave_policy.txt         # source document (fictional)
│   └── evaluation_questions.csv    # 25 questions with expected answers
├── src/basic_rag/
│   ├── config.py                   # all settings: URLs, models, sizes, paths
│   ├── prompts.py                  # answer prompt, shared by query + evals
│   ├── parser.py                   # load a document
│   ├── chunker.py                  # section-aware chunker (used)
│   ├── character_chunker.py        # fixed-size chunker (kept as an option)
│   ├── embedder.py                 # Ollama embeddings
│   ├── vector_store.py             # Qdrant: connect, recreate, insert, search
│   ├── generator.py                # Ollama answer generation
│   ├── reranker.py                 # cross-encoder reranker (used by evals)
│   └── logger.py                   # coloured console output
├── evals/                          # experiments and evaluations (see below)
├── ingest.py                       # build the vector collection
├── query.py                        # ask a question
├── pyproject.toml
└── uv.lock
```

## Requirements

- Python 3.14, managed with [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) at `http://localhost:11434`, with:
  - `all-minilm` for embeddings (384-dimensional vectors)
  - `gemma3:4b` for answers
- [Qdrant](https://qdrant.tech/) at `http://localhost:6333`

Models must be installed in the Ollama instance the app talks to. Models
pulled inside a Docker container are separate from models pulled into
native macOS Ollama.

## Setup

Start Ollama (the native macOS app) and check that the models are there:

```bash
curl http://localhost:11434/api/tags
ollama list

# if needed
ollama pull all-minilm
ollama pull gemma3:4b
```

Start Qdrant. In the development setup it runs in a Docker container named
`qdrant`:

```bash
docker ps              # is it running?
docker start qdrant    # start the existing container
```

Install the Python dependencies from the `basic-rag/` directory:

```bash
uv sync
```

## Configuration

All settings live in [`src/basic_rag/config.py`](src/basic_rag/config.py):

| Setting | Value | Used for |
|---|---|---|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant connection |
| `COLLECTION_NAME` | `hr_leave_policy` | Qdrant collection |
| `VECTOR_SIZE` | `384` | must match the embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | embed + generate endpoints |
| `EMBEDDING_MODEL` | `all-minilm` | document and question embeddings |
| `LLM_MODEL` | `gemma3:4b` | answers, query rewriting/expansion |
| `JUDGE_MODEL` | `gemma3:4b` | grading answers in evals |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | reranking experiments |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `100` | chunking (characters) |
| `TOP_K` | `3` | chunks passed to the LLM |
| `CANDIDATE_K` / `RRF_K` | `20` / `60` | reranking and hybrid experiments |

File paths are built from the project root, so scripts work from any
working directory.

If you change `EMBEDDING_MODEL`, update `VECTOR_SIZE` and re-run ingestion.
Vectors from different embedding models are not compatible, even when
their dimensions match.

## Ingest the document

```bash
uv run python ingest.py
```

This loads the policy, splits it into chunks, embeds each chunk, and stores
them in Qdrant. Run it whenever the document, chunking, or embedding model
changes.

**Ingestion deletes and recreates the collection** every time, so no stale
chunks survive from earlier runs. Only `ingest.py` calls
`recreate_collection()`. Everything else connects with `get_client()`,
which never changes data.

Each chunk is stored with:

- **A deterministic UUID** built from `source + section_id + chunk_index`.
  Re-ingesting the same chunk gives the same ID, and chunks from different
  documents never collide. Ingestion stops with an error if two chunks
  would get the same ID.
- **A payload** containing `text`, `source` (the file name), `section`,
  `section_id`, `section_title`, `parent_section`, `chunk_index`, and
  `document_type`.

## Ask a question

```bash
uv run python query.py
```

The query flow:

1. Embed the question with `all-minilm`.
2. Retrieve the 3 nearest chunks from Qdrant (cosine similarity).
3. Build the prompt from [`prompts.py`](src/basic_rag/prompts.py) with the
   retrieved chunks and the question.
4. Generate the answer with `gemma3:4b` (temperature 0).
5. Print the retrieved chunks, the answer, and timings for each stage.

The prompt tells the model to answer only from the retrieved context. That
is an instruction, not a guarantee. The total time includes the time spent
typing the question, because the timer starts before `input()`.

## Evaluations and experiments

`evals/` is a sandbox for testing retrieval strategies. Each script is
self-contained on purpose. A strategy moves into the main pipeline only
after it proves itself here, and the plan is to re-test as more data is
added.

Run any script from the `basic-rag/` directory with
`uv run python evals/<script>.py`.

| Script | What it measures | Needs the LLM |
|---|---|---|
| `evaluate_retrieval.py` | baseline vector search: Hit Rate, Recall, MRR @3 | no |
| `evaluate_reranking.py` | top 20 from vector search, cross-encoder reranks to 3 | no |
| `evaluate_hybrid_search.py` | vector + BM25 keyword search, fused with RRF | no |
| `evaluate_query_rewriting.py` | LLM rewrites the question before searching | yes |
| `evaluate_query_expansion.py` | LLM generates alternative queries, results merged | yes |
| `evaluate_answers.py` | full pipeline answers graded by an LLM judge | yes |
| `experiment_metadata_filter.py` | one question, with and without a section filter | no |
| `diagnose_retrieval.py` | why section 7.1 ranks where it does for 4 phrasings | no |

The retrieval scripts check whether the expected **section** (for example
`4.1`) appears in the top results. Labels are by section, not by chunk, so
they stay valid when the chunking changes.

`evaluate_answers.py` writes per-question results to
`evals/answer_evaluation_results.csv`. Each run overwrites the file.

The reranker model (`BAAI/bge-reranker-base`) is downloaded from Hugging
Face the first time `evaluate_reranking.py` runs.

### Current baseline (17 October 2026)

| Evaluation | Result |
|---|---|
| Retrieval (vector, top 3) | Hit Rate 96%, Recall 0.94, MRR 0.90 |
| Answer quality (LLM judge) | 97.3% average, 23 of 25 answers perfect |

The answer prompt deliberately contains no examples taken from the
evaluation questions, so these scores aren't inflated.

## Known limitations

- **Questions that compare the user's numbers to a policy limit are
  weak.** For example, "I have 8 unused days. Can I carry all 8?" The
  model does not reliably compare the 8 with the 5-day limit.
- **The judge is the same model as the answerer** (`gemma3:4b`), so
  answer scores are noisy, and the judge can miss contradictions.
- **The evaluation set is small** (25 questions). One question is worth 4
  percentage points.
- **There is no similarity threshold.** Unrelated questions still get
  the top 3 chunks as context.
- **Ingestion handles one document per run** and recreates the collection
  each time.
- **One embedding request per chunk.** Ollama's `/api/embed` endpoint can
  take a batch.
- **No streaming.** The answer appears only after generation finishes.
- **The prompt context omits section titles.** Chunks reach the LLM
  without their section labels.
