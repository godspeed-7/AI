# Pipeline Flow

An end-to-end walkthrough of the two pipelines in this project, step by
step, following one real piece of the policy and one real question
through the system. It also shows where each evaluation experiment plugs
in.

For setup, commands, and the current value of every setting (`TOP_K`,
`CHUNK_SIZE`, model names, …), see [README.md](README.md). This document
refers to settings by name only.

The example data below (chunk text, vectors, scores, the answer) comes
from one real run. It illustrates each step and may drift slightly if
models or settings change.

---

## 1. The big picture

The project has two pipelines that meet at Qdrant:

```text
   INGESTION (offline)                        QUERY (online)
   run when the document changes              run for every question
   ─────────────────────────────              ─────────────────────────────

   documents/policies/*.txt                   "How many unused annual-leave
   (11 AMS documents)                          days can an India-based
          │                                    employee normally carry over?"
          ▼                                            │
   ① Load        parser.py                            ▼
          │                                   ① Embed      embedder.py
          ▼                                            │
   ② Chunk       chunker.py                           ▼
          │                                   ② Retrieve   vector_store.search
          ▼                                            │
   ③ Embed       embedder.py                          ▼
          │                                   ③ Prompt     prompts.py
          ▼                                            │
   ④ Reset       vector_store.py                      ▼
          │                                   ④ Generate   generator.py
          ▼                                            │
   ⑤ Store       vector_store.py                      ▼
          │                                        answer
          ▼                                            ▲
   ┌──────────────────────┐                            │
   │  Qdrant collection   │◄───── nearest chunks ──────┘
   │  "ams_policies"      │       (step ② reads from here)
   │  258 chunks (points) │
   └──────────────────────┘
```

- **Ingestion** turns the document into searchable vectors. Slow and
  rare: run it again only when the document, chunking, or embedding model
  changes.
- **Query** answers one question using what ingestion stored. It only
  reads from Qdrant, never writes.
- **Both use the same embedding model** (`EMBEDDING_MODEL`). A question
  vector can only be compared with chunk vectors made by the same model.

---

## 2. Ingestion pipeline

Script: [`ingest.py`](ingest.py) · Run: `uv run python ingest.py`

The documents are 11 fictional policies for a company called AMS (leave
in India and the US, holidays, travel, benefits, remote work, conduct,
onboarding and exit, an FAQ, and one deliberately outdated leave policy).
We follow **section 4.1 of `leave_policy_india.txt`** through every step.

### ① Load: [`parser.py`](src/basic_rag/parser.py) → `list_documents()`, `load_document()`

| | |
|---|---|
| **In** | every `.txt` file in `documents/policies/` (11 files) |
| **Out** | one string per document (59,940 characters in total; `leave_policy_india.txt` is 9,874) |
| **Settings** | `POLICIES_DIR` |

Nothing clever here: read each file as text. The file name is kept,
because it becomes every chunk's `source`.

### ② Chunk: [`chunker.py`](src/basic_rag/chunker.py) → `chunk_text()`

| | |
|---|---|
| **In** | one document string at a time |
| **Out** | a list of chunk dicts: 258 in total, 35 from `leave_policy_india.txt` |
| **Settings** | `CHUNK_SIZE`, `CHUNK_OVERLAP` (in characters) |

Each document is chunked separately, so a chunk never mixes text from two
documents.

Two phases:

1. **Split by heading.** Every numbered heading (`4.`, `4.1`, …) starts a
   section. Sub-sections remember their parent.
2. **Split long sections.** Sections longer than `CHUNK_SIZE` are cut into
   pieces, but only at the end of a line or a sentence, so every chunk
   starts and ends on a complete thought. `CHUNK_OVERLAP` is 0: with clean
   cuts, no sentence is split across two chunks, so nothing needs
   repeating. Most sections are short and stay as one chunk.

Every chunk also gets the document's title and version, read from the
file's header (lines 2–3). Without it, only the INTRODUCTION chunk would
say "INDIA" or "Version 2.1", and section 4.1 would look the same in the
India, US, and old v2.0 policies.

Section 4.1 becomes:

```python
{
    "document_title": "EMPLOYEE LEAVE POLICY (INDIA), Version 2.1",
    "section":        "4.1 Standard carry-over limit",
    "section_id":     "4.1",
    "section_title":  "Standard carry-over limit",
    "parent_section": "4. ANNUAL LEAVE CARRY-OVER",
    "chunk_index":    0,
    "text": "Employees may carry over up to 5 unused annual-leave days "
            "from one leave year into the next leave year.",
}
```

> Alternative not in use: [`character_chunker.py`](src/basic_rag/character_chunker.py)
> cuts at fixed character counts, ignoring headings. It returns plain strings,
> so it would need adapting before it could replace this step.

### ③ Embed: [`embedder.py`](src/basic_rag/embedder.py) → `embed_chunks()`

| | |
|---|---|
| **In** | the 258 chunk dicts |
| **Out** | the same dicts, each with an added `"embedding"` (384 numbers) |
| **Settings** | `EMBEDDING_MODEL` (served by Ollama) |

Before embedding, each chunk gets its section heading added in front.
This text is what gets embedded:

```text
Section: 4.1 Standard carry-over limit
Parent section: 4. ANNUAL LEAVE CARRY-OVER

Employees may carry over up to 5 unused annual-leave days from one leave
year into the next leave year.
```

Result: a vector of 384 numbers, starting `[0.023, -0.037, 0.084, 0.010, …]`.

Why add the heading? The sentence alone never says "annual leave
carry-over" as a topic; the heading does. Adding it makes the vector
closer to questions about carry-over. Only the embedding sees this
prefix; the stored text stays plain.

### ④ Reset: [`vector_store.py`](src/basic_rag/vector_store.py) → `get_client()`, `recreate_collection()`

| | |
|---|---|
| **In** | nothing |
| **Out** | an empty collection (`VECTOR_SIZE` dimensions, cosine distance) |
| **Settings** | `QDRANT_URL`, `COLLECTION_NAME`, `VECTOR_SIZE` |

⚠️ **Deletes everything** in the collection, so no stale chunks from an
earlier run survive. Only `ingest.py` calls `recreate_collection()`.

### ⑤ Store: [`vector_store.py`](src/basic_rag/vector_store.py) → `insert_chunks()`

| | |
|---|---|
| **In** | each document's embedded chunks + its file name as `source` |
| **Out** | 258 points in Qdrant |

Each chunk becomes a **point** with three parts:

```text
id       4e6676fc-fca4-501d-a0a4-ad25d188eeca
         uuid5("leave_policy_india.txt#4.1#0"), the same every run;
         the US policy's 4.1 gets a different ID

vector   [0.023, -0.037, 0.084, 0.010, …]   (384 numbers, for matching)

payload  {text, source, section, section_id, section_title,
          parent_section, chunk_index, document_type}
         (returned with search results)
```

---

## 3. Query pipeline

Script: [`query.py`](query.py) · Run: `uv run python query.py`

We follow the question **"How many unused annual-leave days can an
India-based employee normally carry over?"** The correct answer, from the
current India policy (`leave_policy_india.txt` section 4.1), is **5 days**.
This run shows a real failure, which makes it a useful example.

### ① Embed: [`embedder.py`](src/basic_rag/embedder.py) → `generate_embedding()`

| | |
|---|---|
| **In** | the question string |
| **Out** | a 384-number vector, starting `[0.025, 0.015, 0.003, 0.039, …]` |

Same model as ingestion step ③, but no heading prefix: the question is
embedded as typed.

### ② Retrieve: [`vector_store.py`](src/basic_rag/vector_store.py) → `search()`

| | |
|---|---|
| **In** | the question vector |
| **Out** | the `TOP_K` nearest chunks, best first (3 in this run) |

Qdrant compares the question vector with all 258 chunk vectors (cosine
similarity: 1.0 = same direction) and returns the closest:

| Rank | Document | Section | Score |
|---|---|---|---|
| 1 | `leave_policy_india_v2_0.txt` (superseded) | 4.1 Standard carry-over limit | 0.680 ⚠️ |
| 2 | `leave_policy_india.txt` (current) | 4.1 Standard carry-over limit | 0.670 ✅ |
| 3 | `leave_policy_us.txt` | 4.1 Carry-over limit | 0.603 |

The right section was retrieved, but the **outdated version ranked
first**. Both texts are almost identical apart from the number, so vector
search can't tell which one is current. The US policy's 4.1 also came in,
because it's about the same topic.

### ③ Prompt: [`prompts.py`](src/basic_rag/prompts.py) → `build_prompt()`

| | |
|---|---|
| **In** | the question + the 3 retrieved chunks |
| **Out** | one prompt string |

The prompt has three parts:

```text
[rules]     answer only from the context, don't confuse leave types,
            apply numbers to the user's scenario, say so if the answer
            isn't in the context ...

[context]   the text of the 3 chunks, separated by blank lines

[question]  How many unused annual-leave days can an India-based
            employee normally carry over?
```

Note that the context is only chunk text. The document name and "STATUS:
SUPERSEDED" line aren't included, so the model has no way to know which
chunk is outdated.

`evals/evaluate_answers.py` uses this same function, so the eval tests
the real prompt.

### ④ Generate: [`generator.py`](src/basic_rag/generator.py) → `generate_answer()`

| | |
|---|---|
| **In** | the prompt |
| **Out** | the answer text (~8–10 seconds on an M4 Mac) |
| **Settings** | `LLM_MODEL`, `TEMPERATURE` |

> An India-based employee may normally carry over up to 8 unused
> annual-leave days from one leave year into the next leave year.

❌ **Wrong.** The current limit is 5 days; 8 days comes from the
superseded 2024 version, which ranked first.

This is exactly the kind of failure the expanded dataset was built to
expose (see the `outdated` question category in § 4). Possible fixes to
test as experiments: filter out superseded documents at search time
(experiment C), add the document name and status to the prompt context,
or stop ingesting superseded documents.

---

## 4. Where the experiments plug in

Everything in [`evals/`](evals/) is an **experiment**: none of it is part
of `query.py` yet. Each one changes or inspects one step of the query
pipeline, then measures the effect.

```text
   question
      │
      ├╌╌ [A] Query rewriting ╌╌╌╌ LLM rewrites the question first
      ├╌╌ [B] Query expansion ╌╌╌╌ LLM adds 2 alternative questions;
      │                            all are searched, results merged
      ▼
   ① Embed
      │
      ▼
   ② Retrieve ◄╌╌ [C] Metadata filter ╌╌ only search chunks with
      │                                   e.g. section_id = "4.1"
      │       ◄╌╌ [D] Hybrid search ╌╌╌╌ also run BM25 keyword search,
      │                                   fuse both rankings (RRF)
      │       ◄╌╌ [E] Reranking ╌╌╌╌╌╌╌╌ fetch CANDIDATE_K, cross-
      │                                   encoder re-scores, keep TOP_K
      │       ◄╌╌ [F] Diagnose ╌╌╌╌╌╌╌╌╌ inspect why a section ranks
      │                                   where it does (no change)
      ▼
   top chunks ══════════ 📏 RETRIEVAL METRICS measured here
      │                     Hit Rate · Recall · MRR
      ▼
   ③ Prompt
      │
      ▼
   ④ Generate
      │
      ▼
   answer ══════════════ 📏 ANSWER QUALITY measured here
                            LLM judge: correctness · context support ·
                            completeness
```

### Experiment reference

| | Experiment | Script | Changes which step | Measured by | LLM? |
|---|---|---|---|---|---|
| — | **Baseline** | `evaluate_retrieval.py` | nothing (plain pipeline) | retrieval metrics | no |
| A | Query rewriting | `evaluate_query_rewriting.py` | before ① | retrieval metrics vs baseline | yes |
| B | Query expansion | `evaluate_query_expansion.py` | before ①, and merges ② | retrieval metrics + run time | yes |
| C | Metadata filter | `experiment_metadata_filter.py` | ② (filter) | printed results, one question | no |
| D | Hybrid search | `evaluate_hybrid_search.py` | ② (adds BM25 + RRF) | retrieval metrics vs baseline | no |
| E | Reranking | `evaluate_reranking.py` | after ② (`CANDIDATE_K` → `TOP_K`) | retrieval metrics vs baseline | no |
| F | Diagnose | `diagnose_retrieval.py` | none (inspects ②) | similarity + rank, 4 phrasings | no |
| — | **Answer quality** | `evaluate_answers.py` | nothing (whole pipeline) | LLM judge, 0–6 per question | yes |

For run times and side effects (which scripts are slow, which file gets
overwritten), see [README.md → Run the evaluations](README.md#run-the-evaluations).

### The evaluation questions

[`documents/evaluation_questions.csv`](documents/evaluation_questions.csv)
holds 150 questions with these columns:

| Column | Example |
|---|---|
| `question` | Can an L6 director fly business class? |
| `expected_answer` | Yes, on flights scheduled for more than 6 hours; otherwise economy. |
| `expected_source` | `travel_expense_policy.txt#4.1`. Every section that contains the answer, as `document#section`, separated by `;` |
| `category` | one of the 8 below |
| `split` | `dev` (90 questions, for tuning) or `test` (60, for the final check) |

| Category | Count | What it tests |
|---|---|---|
| `lookup` | 30 | a fact stated in one place |
| `location` | 20 | picking the right office or country |
| `code_grade` | 20 | exact form codes and job grades |
| `confusable` | 20 | similar-sounding rules (carry-over vs carry-forward, …) |
| `two_document` | 20 | the answer needs two documents |
| `casual` | 15 | informal wording ("can i chill at home on fridays?") |
| `outdated` | 10 | the current rule, not the superseded 2024 one |
| `unanswerable` | 15 | not in any document; the right answer is "I can't tell" |

Unanswerable questions have no `expected_source`, so the retrieval
scripts skip them (135 questions are scored). `evaluate_answers.py` uses
all 150. The scripts don't use the `split` column yet.

### The two kinds of measurement

**Retrieval metrics** (at "top chunks") ask: *did we find the right
section?* They compare each retrieved chunk's `source#section_id` with
the question's `expected_source`. They're reported "@3" because `TOP_K`
chunks (3) are retrieved.

| Metric | Meaning | Example |
|---|---|---|
| Hit Rate | % of questions where any expected section is retrieved | 119 of 135 → 88.1% |
| Recall | share of expected sections found, averaged | expects 4.1 + 4.3, finds 4.1 → 0.5 |
| MRR | 1 / rank of the first correct chunk, averaged | 1st → 1.0, 2nd → 0.5, 3rd → 0.33 |

**Answer quality** (at "answer") asks: *was the final answer good?* A
judge LLM scores each answer 0–2 on correctness, context support, and
completeness.

Why both? If retrieval misses the right section, the answer can't be
right, so a bad answer score with a good retrieval score points at the
prompt or the LLM, and a bad retrieval score points at steps ①–②.

### Current baseline (17 October 2026)

This is the only place the baseline is recorded; update it whenever a
change is promoted into the pipeline (see § 6).

Measured on the AMS dataset (11 documents, 258 chunks, 150 questions):

| Measure | Result |
|---|---|
| Retrieval (vector search, @3, 135 scored questions) | Hit Rate 88.1%, Recall 0.81, MRR 0.80 |
| Answer quality | not yet measured on this dataset |

Retrieval was Hit Rate 86.7%, Recall 0.79, MRR 0.78 before chunks got
their document title (in the embedding text and in the prompt).
Cutting only at line or sentence ends left these numbers unchanged.

The answer prompt contains no examples taken from the evaluation
questions, so these scores aren't inflated.

For history: on the original single-document dataset (35 chunks, 25
questions), retrieval scored Hit Rate 96%, Recall 0.94, MRR 0.90, and
answer quality 97.3%. The two datasets aren't comparable; the AMS one is
deliberately harder.

---

## 5. Ingestion-side knobs (no experiment scripts yet)

The experiments above all target the query side. These ingestion choices
also affect results, but changing any of them means **re-running
`ingest.py`** before re-running the evals:

| Knob | Where it's set | Currently |
|---|---|---|
| Chunking strategy | which chunker `ingest.py` imports | section-aware (`chunker.py`) |
| Chunk size / overlap | `CHUNK_SIZE`, `CHUNK_OVERLAP` in `config.py` | see README |
| Heading prefix in embeddings | `embedder.py` → `embed_chunks()` | on |
| Embedding model | `EMBEDDING_MODEL` + `VECTOR_SIZE` in `config.py` | see README |

---

## 6. From experiment to pipeline

How a winning experiment becomes part of `query.py`:

```text
 1. Experiment     write or tweak the script in evals/
        │
        ▼
 2. Compare        run it against the baseline on the same questions
        │          (more data → more trustworthy comparison)
        ▼
 3. Decide         clearly better on the metrics, and worth the extra
        │          time/complexity? If not, it stays in evals/
        ▼
 4. Promote        move the strategy's code into src/basic_rag/ and call
        │          it from query.py
        ▼
 5. New baseline   re-run evaluate_retrieval.py and evaluate_answers.py;
                   record the numbers in § 4 "Current baseline"
```
