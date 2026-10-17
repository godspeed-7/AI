# Basic RAG: HR Leave Policy

A small Retrieval-Augmented Generation (RAG) project built from scratch in
Python, without LangChain or similar frameworks, so every step of the
pipeline stays visible. It answers employee questions from the policy
documents of **AMS**, a fictional software company with offices in
Bengaluru, Pune, and Austin, using:

- **Ollama** for embeddings and answer generation
- **Qdrant** as the vector database

There are two pipelines:

```text
Ingestion (ingest.py):  load → chunk → embed → store in Qdrant
Query     (query.py):   embed question → retrieve chunks → build prompt → generate answer
```

**This README covers how to set up and run the project.** For how it works
(a step-by-step walkthrough with real example data, where each evaluation
experiment plugs in, the metrics, and the current baseline), see
[PIPELINE_FLOW.md](PIPELINE_FLOW.md).

## Project layout

```text
basic-rag/
├── documents/
│   ├── policies/                   # the 10 AMS documents that get ingested
│   │   ├── company_overview.txt          # offices, grades, systems, contacts
│   │   ├── leave_policy_india.txt        # Bengaluru and Pune leave (v2.1)
│   │   ├── leave_policy_us.txt           # Austin leave (PTO)
│   │   ├── holiday_calendar_2026.txt     # holidays per office
│   │   ├── travel_expense_policy.txt     # travel limits by grade, forms
│   │   ├── benefits_policy.txt           # insurance, learning, wellness
│   │   ├── remote_hybrid_work_policy.txt # office days, remote work
│   │   ├── code_of_conduct.txt           # conduct, harassment, gifts
│   │   ├── onboarding_exit_policy.txt    # probation, notice, settlement
│   │   └── hr_faq.txt                    # practical everyday questions
│   └── evaluation_questions.csv    # 148 questions with expected answers
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
├── evals/                          # experiments and evaluations
├── ingest.py                       # build the vector collection
├── query.py                        # ask a question
├── README.md                       # setup and running (this file)
├── PIPELINE_FLOW.md                # how the pipelines work
├── pyproject.toml
└── uv.lock
```

Every Python file starts with a docstring explaining what it does and how
it fits in. In VS Code, hover over a function name to see its docstring.

## Requirements

- Python 3.14, managed with [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/), with the embedding and answer models
  from [Configuration](#configuration) installed
- [Qdrant](https://qdrant.tech/)

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
| `COLLECTION_NAME` | `ams_policies` | Qdrant collection |
| `VECTOR_SIZE` | `384` | must match the embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | embed + generate endpoints |
| `EMBEDDING_MODEL` | `all-minilm` | document and question embeddings |
| `LLM_MODEL` | `gemma3:4b` | answers, query rewriting/expansion |
| `JUDGE_MODEL` | `gemma3:4b` | grading answers in evals |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | reranking experiment |
| `TEMPERATURE` | `0` | repeatable LLM output |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `0` | chunking (characters) |
| `TOP_K` | `3` | chunks passed to the LLM |
| `CANDIDATE_K` / `RRF_K` | `20` / `60` | reranking and hybrid experiments |

File paths are built from the project root, so scripts work from any
working directory.

If you change `EMBEDDING_MODEL`, update `VECTOR_SIZE` and re-run ingestion.
Vectors from different embedding models are not compatible, even when
their dimensions match. Changing the chunking settings also needs a
re-ingest.

## Running it

Run every command from the `basic-rag/` directory.

### Ingest the document

```bash
uv run python ingest.py
```

It ingests every `.txt` file in `documents/policies/`. Run it once before
the first query, then again whenever a document, the chunking settings,
or the embedding model change. It takes a few seconds.

> ⚠️ **Ingestion deletes and recreates the collection every time.** Only
> `ingest.py` calls `recreate_collection()`. Everything else connects with
> `get_client()`, which never changes data.

**To add a document**, save it as a `.txt` file in `documents/policies/`
and re-run ingestion. The chunker splits on numbered headings, so:

- Give every section a numbered heading on its own line (`3.`, `3.1`, …).
- Don't start any other line with a number followed by a space; the
  chunker would treat it as a heading. Write table rows like
  `Republic Day | 26 January 2026 | Monday`, not `26 January | ...`.

### Ask a question

```bash
uv run python query.py
```

Type a question about the leave policy. The script prints the retrieved
chunks, then the answer, with timings for each step. Expect about 10
seconds, most of it answer generation. The total time includes the time
spent typing the question, because the timer starts before `input()`.

### Run the evaluations

```bash
uv run python evals/<script>.py
```

`evals/` is a sandbox for testing retrieval strategies. Each script is
self-contained on purpose, and a strategy moves into the main pipeline
only after it proves itself there. What each script tests, and which
pipeline step it changes, is described in
[PIPELINE_FLOW.md § 4](PIPELINE_FLOW.md#4-where-the-experiments-plug-in).

Things to know before running them:

- **They read from the current collection**, so run `ingest.py` first if
  anything changed.
- **Scripts that call the LLM are slow** with 148 questions (rough
  estimates):
  - `evaluate_query_rewriting.py` and `evaluate_query_expansion.py` take
    10–20 minutes each
  - `evaluate_answers.py` takes about an hour

  The others finish in under a minute.
- **`evaluate_answers.py` overwrites `evals/answer_evaluation_results.csv`**
  on every run. Copy the file first if you want to compare with a
  previous run. Add `-u` (`uv run python -u evals/...`) to see progress
  as it happens.
- **`evaluate_reranking.py` downloads the reranker model** from Hugging
  Face on its first run.

## Known limitations

- **Questions that compare the user's numbers to a policy limit are
  weak.** For example, "I have 8 unused days. Can I carry all 8?" The
  model does not reliably compare the 8 with the 5-day limit.
- **"Answer only from the context" is a prompt instruction, not a
  guarantee.** The model can still add or misstate facts.
- **The judge is the same model as the answerer**, so answer scores are
  noisy, and the judge can miss contradictions.
- **The `split` column isn't used yet.** Every eval script runs on all
  questions, so there's no held-out test set in practice.
- **There is no similarity threshold.** Unrelated questions still get the
  top chunks as context.
- **Ingestion rebuilds everything every time.** Changing one document
  re-embeds all of them. Fine at 239 chunks, slow at thousands.
- **One embedding request per chunk.** Ollama's `/api/embed` endpoint can
  take a batch.
- **No streaming.** The answer appears only after generation finishes.
- **The prompt context omits section titles.** Chunks reach the LLM
  without their section labels.
