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
   (10 AMS documents)                          days can an India-based
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
   │  239 chunks (points) │
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

The documents are 10 fictional policies for a company called AMS (leave
in India and the US, holidays, travel, benefits, remote work, conduct,
onboarding and exit, and an FAQ).
We follow **section 4.1 of `leave_policy_india.txt`** through every step.

### ① Load: [`parser.py`](src/basic_rag/parser.py) → `list_documents()`, `load_document()`

| | |
|---|---|
| **In** | every `.txt` file in `documents/policies/` (10 files) |
| **Out** | one string per document (56,406 characters in total; `leave_policy_india.txt` is 9,874) |
| **Settings** | `POLICIES_DIR` |

Nothing clever here: read each file as text. The file name is kept,
because it becomes every chunk's `source`.

### ② Chunk: [`chunker.py`](src/basic_rag/chunker.py) → `chunk_text()`

| | |
|---|---|
| **In** | one document string at a time |
| **Out** | a list of chunk dicts: 239 in total, 35 from `leave_policy_india.txt` |
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
say "INDIA" or "Version 2.1", and the carry-over rule in section 4.1
would look much the same in the India and US leave policies.

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
| **In** | the 239 chunk dicts |
| **Out** | the same dicts, each with an added `"embedding"` (768 numbers) |
| **Settings** | `EMBEDDING_MODEL` (`nomic-embed-text`, served by Ollama), `EMBED_DOCUMENT_PREFIX` |

Before embedding, each chunk gets the model's task prefix
(`search_document:`), its document title, and its section heading
added in front. This text is what gets embedded:

```text
search_document: Document: EMPLOYEE LEAVE POLICY (INDIA), Version 2.1
Section: 4.1 Standard carry-over limit
Parent section: 4. ANNUAL LEAVE CARRY-OVER

Employees may carry over up to 5 unused annual-leave days from one leave
year into the next leave year.
```

Result: a vector of 768 numbers, starting `[0.008, 0.041, -0.174, -0.020, …]`.

Why add them? The sentence alone never says "annual leave carry-over" as
a topic, or that it's the India policy; the heading and title do. Adding
them makes the vector closer to questions about India carry-over. The
`search_document:` prefix is required by nomic-embed-text, which was
trained with it (questions get `search_query:` instead). Only the
embedding sees these prefixes; the stored text stays plain.

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
| **Out** | 239 points in Qdrant |

Each chunk becomes a **point** with three parts:

```text
id       4e6676fc-fca4-501d-a0a4-ad25d188eeca
         uuid5("leave_policy_india.txt#4.1#0"), the same every run;
         the US policy's 4.1 gets a different ID

vector   [0.008, 0.041, -0.174, -0.020, …]   (768 numbers, for matching)

payload  {text, source, document_title, section, section_id,
          section_title, parent_section, chunk_index, document_type}
         (returned with search results)
```

---

## 3. Query pipeline

Script: [`query.py`](query.py) · Run: `uv run python query.py`

We follow the question **"How many unused annual-leave days can an
India-based employee normally carry over?"** The correct answer, from the
India policy (`leave_policy_india.txt` section 4.1), is **5 days**.

### ① Embed: [`embedder.py`](src/basic_rag/embedder.py) → `generate_embedding()`

| | |
|---|---|
| **In** | the question string |
| **Out** | a 768-number vector, starting `[0.010, 0.042, -0.196, -0.017, …]` |

Same model as ingestion step ③. The question gets only the model's
`search_query:` prefix, no title or heading.

### ② Retrieve: [`vector_store.py`](src/basic_rag/vector_store.py) → `search()`

| | |
|---|---|
| **In** | the question vector |
| **Out** | the `TOP_K` nearest chunks, best first (3 in this run) |

Qdrant compares the question vector with all 239 chunk vectors (cosine
similarity: 1.0 = same direction) and returns the closest:

| Rank | Document | Section | Score |
|---|---|---|---|
| 1 | `leave_policy_india.txt` | 4.1 Standard carry-over limit | 0.883 ✅ |
| 2 | `leave_policy_india.txt` | 4.2 Conditions | 0.857 |
| 3 | `leave_policy_india.txt` | 11 Quick reference table | 0.855 |

The right section ranked first. All three come from the India policy:
the question says "India-based", and every chunk's embedding text now
starts with its document title, so the US policy's similar 4.1 rule
scores lower.

Scores are only comparable within one embedding model: nomic-embed-text
scores everything higher than all-minilm did (a weak match here can
still be ~0.6), so "0.88" doesn't mean the same as 0.88 elsewhere.

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

[context]   the 3 chunks, each under a label naming its document and
            section, separated by blank lines:
            [EMPLOYEE LEAVE POLICY (INDIA), Version 2.1 | 4.1 Standard
            carry-over limit]
            Employees may carry over up to 5 unused annual-leave days...

[question]  How many unused annual-leave days can an India-based
            employee normally carry over?
```

The labels let the model tell apart similar rules from different
documents, e.g. India's 5-day and the US policy's 10-day carry-over.

`evals/evaluate_answers.py` uses this same function, so the eval tests
the real prompt.

### ④ Generate: [`generator.py`](src/basic_rag/generator.py) → `generate_answer()`

| | |
|---|---|
| **In** | the prompt |
| **Out** | the answer text (~8–10 seconds on an M4 Mac) |
| **Settings** | `LLM_MODEL`, `TEMPERATURE` |

> According to the Employee Leave Policy (INDIA), Version 2.1, employees
> may carry over up to 5 unused annual-leave days from one leave year
> into the next. This carry-over must be used by 31 March of the
> following year, subject to Section 4.3.

✅ **Correct** (5 days), with the use-by deadline from section 4.2.

---

## 4. Where the experiments plug in

Scripts live in three folders:
- [`evals/`](evals/) **measures** the current pipeline (retrieval and
  answer quality).
- [`experiments/`](experiments/) **tries a change** to one step of the
  query pipeline and measures the effect. None of them is part of
  `query.py` yet.
- [`tools/`](tools/) **investigates** one specific problem, without
  measuring or changing anything.

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
      │       ◄╌╌ [G] Context compression ╌╌ shrink the chunks'
      │                                       text before the prompt
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
| — | **Baseline** | `evals/evaluate_retrieval.py` | nothing (plain pipeline) | retrieval metrics | no |
| A | Query rewriting | `experiments/evaluate_query_rewriting.py` | before ① | retrieval metrics vs baseline | yes |
| B | Query expansion | `experiments/evaluate_query_expansion.py` | before ①, and merges ② | retrieval metrics + run time | yes |
| C | Metadata filter | `experiments/experiment_metadata_filter.py` | ② (filter) | printed results, one question | no |
| D | Hybrid search | `experiments/evaluate_hybrid_search.py` | ② (adds BM25 + RRF) | retrieval metrics vs baseline | no |
| E | Reranking | `experiments/evaluate_reranking.py` | after ② (`CANDIDATE_K` → `TOP_K`) | retrieval metrics vs baseline | no |
| F | Diagnose | `tools/diagnose_retrieval.py` | none (inspects ②) | similarity + rank, 4 phrasings | no |
| G | Context compression | `experiments/evaluate_context_compression.py` | between ② and ③ | LLM judge + context reduction + time, per strategy | yes |
| — | **Answer quality** | `evals/evaluate_answers.py` | nothing (whole pipeline) | LLM judge, 0–6 per question | yes |

For run times and side effects (which scripts are slow, which file gets
overwritten), see [README.md → Run the evaluations, experiments, and tools](README.md#run-the-evaluations-experiments-and-tools).

### The evaluation questions

[`documents/evaluation_questions.csv`](documents/evaluation_questions.csv)
holds 148 questions with these columns:

| Column | Example |
|---|---|
| `question` | Can an L6 director fly business class? |
| `expected_answer` | Yes, on flights scheduled for more than 6 hours; otherwise economy. |
| `expected_source` | `travel_expense_policy.txt#4.1`. Every section that contains the answer, as `document#section`, separated by `;` |
| `category` | one of the 8 below |
| `split` | `dev` (89 questions, for tuning) or `test` (59, for the final check) |

| Category | Count | What it tests |
|---|---|---|
| `lookup` | 30 | a fact stated in one place |
| `location` | 20 | picking the right office or country |
| `code_grade` | 20 | exact form codes and job grades |
| `confusable` | 20 | similar-sounding rules (carry-over vs carry-forward, …) |
| `two_document` | 20 | the answer needs two documents |
| `casual` | 15 | informal wording ("can i chill at home on fridays?") |
| `outdated` | 8 | India leave rules that changed between policy versions; the old version is no longer ingested, so these are now ordinary lookups |
| `unanswerable` | 15 | not in any document; the right answer is "I can't tell" |

Unanswerable questions have no `expected_source`, so the retrieval
scripts skip them (133 questions are scored). `evaluate_answers.py` uses
all 148. The scripts don't use the `split` column yet.

### The two kinds of measurement

**Retrieval metrics** (at "top chunks") ask: *did we find the right
section?* They compare each retrieved chunk's `source#section_id` with
the question's `expected_source`. They're reported "@3" because `TOP_K`
chunks (3) are retrieved.

| Metric | Meaning | Example |
|---|---|---|
| Hit Rate | % of questions where any expected section is retrieved | 124 of 133 → 93.2% |
| Recall | share of expected sections found, averaged | expects 4.1 + 4.3, finds 4.1 → 0.5 |
| MRR | 1 / rank of the first correct chunk, averaged | 1st → 1.0, 2nd → 0.5, 3rd → 0.33 |

**Answer quality** (at "answer") asks: *was the final answer good?* A
judge LLM ([`judge.py`](src/basic_rag/judge.py), shared by
`evaluate_answers.py` and the compression experiment) scores each answer
0–2 on correctness, context support, and completeness.

Why both? If retrieval misses the right section, the answer can't be
right, so a bad answer score with a good retrieval score points at the
prompt or the LLM, and a bad retrieval score points at steps ①–②.

### Current baseline (17 October 2026)

This is the only place the baseline is recorded; update it whenever a
change is promoted into the pipeline (see § 6).

Measured on the AMS dataset (10 documents, 239 chunks, 148 questions),
with `TOP_K` = 3:

| Measure | Result |
|---|---|
| Retrieval (vector search, @3, 133 scored questions) | Hit Rate 93.2%, Recall 0.86, MRR 0.85 |
| Answer quality (all 148 questions) | 92.7% (5.56/6): correctness 1.83, context support 1.89, completeness 1.84; 125 answers perfect |

The weakest category is `casual` (retrieval Hit Rate 73%, answers 70%):
informal, vague wording like "how many leaves do i get". Next weakest
is `unanswerable` (answers 79%): the model sometimes answers from a
related chunk instead of saying it can't tell (e.g. sabbatical days).

How answer quality got here (same 148 questions):
- 93.8% with `TOP_K` = 5 and 94.0% with `TOP_K` = 3: no real
  difference, so 3 was kept (shorter prompt, faster).
- 92.7% after rewording prompt rule 7 ("only answer if the context
  directly addresses the question"). Checking the answers that changed
  showed one real fix (Austin restricted holidays) and no real
  regressions; the lower score came from judge noise.
- The judge's score for the same answer can vary by ±2 points, so
  differences of 1–2% between runs are noise.

How retrieval got here (same questions within each step):
- Hit Rate 86.7%, Recall 0.79, MRR 0.78: the first AMS run, with 11
  documents, including a superseded 2024 India leave policy.
- No change from cutting chunks only at line or sentence ends.
- 88.1%, 0.81, 0.80 after chunks got their document title (in the
  embedding text and in the prompt).
- 89.5%, 0.83, 0.83 after removing the superseded policy and its 2
  questions (from here on, 133 questions instead of 135).
- 93.2%, 0.86, 0.85 after switching the embedding model from
  all-minilm (384 numbers) to nomic-embed-text (768), with its
  search_document: / search_query: prefixes.

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
 1. Experiment     write or tweak the script in experiments/
        │
        ▼
 2. Compare        run it against the baseline on the same questions
        │          (more data → more trustworthy comparison)
        ▼
 3. Decide         clearly better on the metrics, and worth the extra
        │          time/complexity? If not, it stays in experiments/
        ▼
 4. Promote        move the strategy's code into src/basic_rag/ and call
        │          it from query.py
        ▼
 5. New baseline   re-run evaluate_retrieval.py and evaluate_answers.py;
                   record the numbers in § 4 "Current baseline"
```
