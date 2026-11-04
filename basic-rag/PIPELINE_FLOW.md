# Pipeline Flow

An end-to-end walkthrough of the two pipelines in this project, step by
step, following one real piece of the policy and one real question
through the system. It also shows where each evaluation experiment plugs
in, and (§ 7) which RAG technique belongs at which step.

For setup, commands, and the current value of every setting (`TOP_K`,
`CHUNK_SIZE`, model names, …), see [README.md](README.md). This document
refers to settings by name only.

For the general choices behind those settings (chunking, metrics, search,
and eval), see [RAG_CHEAT_SHEET.md](RAG_CHEAT_SHEET.md).

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

   ams-data/policies/*.txt                    "How many unused annual-leave
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
| **In** | every `.txt` file in `ams-data/policies/` (10 files) |
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
      ├╌╌ [H] Query routing ╌╌╌╌╌╌ LLM picks 1–2 policy files (or "all");
      │                            ② searches only those (a filter as in [C])
      ▼
   ① Embed
      │                ┌╌╌ [C] Metadata filter ╌╌ only search chunks with
      ▼                ╎                          e.g. section_id = "4.1"
   ② Retrieve ◄╌╌╌╌╌╌╌╌┤
      │                ╎
      │                └╌╌ [D] Hybrid search ╌╌╌╌ also run BM25 keyword search,
      │                                           fuse both rankings (RRF)
      │
      │       ◄╌╌ [F] Diagnose ╌╌╌╌╌╌╌╌╌ inspect why a section ranks
      │                                   where it does (no change)
      │
      │       ◄╌╌ [E] Reranking ╌╌╌╌╌╌╌╌ ② fetches CANDIDATE_K instead,
      │                                   cross-encoder re-scores them,
      │                                   keep TOP_K
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
| H | Query routing | [`ams-assistant/experiments/evaluate_routing.py`](../ams-assistant/experiments/evaluate_routing.py) (ams-assistant only) | before ①, filters ② | retrieval metrics vs baseline + router accuracy | yes |
| — | **Answer quality** | `evals/evaluate_answers.py` | nothing (whole pipeline) | LLM judge, 0–6 per question | yes |

**H result** (ams-assistant, 31 October 2026, 133 questions): Hit Rate
92.48% → 78.20%, 4 fixed / 23 broken. The router picked all expected
files for 88 of 133, wrong files for 24, and never said "all". The main
failure: a question naming India was sent to the India leave policy
even when the answer was in travel or exit. Not promoted. Re-test once
the dataset is larger.

For run times and side effects (which scripts are slow, which file gets
overwritten), see [README.md → Run the evaluations, experiments, and tools](README.md#run-the-evaluations-experiments-and-tools).

### The evaluation questions

[`ams-data/evaluation_questions.csv`](../ams-data/evaluation_questions.csv)
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

---

## 7. Which technique, at which step

Every RAG technique worth knowing, hung on the step of the pipeline it
changes, so you can see what exists at each step and pick by symptom.
The diagram is the map; the notes below it say when to reach for each
one.

The steps are named, not numbered: there are more of them than the
four in § 3, because many techniques add a step of their own (route,
fuse, rerank, verify). Letters [A]–[H] are the experiments in § 4.

Status, for **ams-assistant** (where the pipeline is being built)
unless marked otherwise:

| | |
|---|---|
| ✅ | in use |
| 🧪 | tried in an experiment, not in the default pipeline |
| ⏭ | next on the plan |
| ⬜ | not tried yet |
| ✗ | skipped, with the reason |

### The map

```text
   INGESTION (offline)
   ───────────────────
   handbooks (.txt)
      │
      ▼
   LOAD / PARSE
      │     ├╌ Plain-text loader ................. ✅
      │     └╌ PDF/Word/HTML loaders · OCR ....... ✗ every source is .txt
      ▼
   CHUNK
      │     ├╌ Structure-aware (one section) ..... ✅
      │     ├╌ Contextual chunk header ........... ✅ breadcrumb +
      │     │                                         "About this chapter"
      │     ├╌ Contextual retrieval (LLM-written)  ⬜
      │     ├╌ Semantic chunking ................. ⬜
      │     ├╌ Parent-child chunks ............... ⬜
      │     ├╌ Fixed-size (+ overlap) ............ ✗ cuts rules in half
      │     └╌ RAPTOR (tree of summaries) ........ ✗ handbooks are small
      ▼
   METADATA
      │     ├╌ department · handbook · chapter ·
      │     │  section · reference … (8 fields) .. ✅
      │     ├╌ country (India / US / both) ....... ⏭ needed by self-query
      │     └╌ Stable chunk IDs .................. ⬜ (basic-rag ✅)
      ▼
   EMBED
      │     ├╌ Dense: nomic-embed-text + prefixes  ✅
      │     ├╌ Sparse vectors (BM25 / SPLADE) .... ⏭ with hybrid search
      │     └╌ Multi-vector · ColBERT ............ ✗ 370 chunks
      ▼
   INDEX (Qdrant)
            ├╌ Exact / brute-force search ........ ✅ Qdrant scans all 370
            ├╌ ANN: HNSW · IVF ................... ✗ built by Qdrant itself
            │                                         on big collections
            ├╌ Quantization ...................... ✗ fits in memory
            ├╌ Payload index ..................... ⬜ once filters are used
            └╌ Multi-tenancy ..................... ✗ one company, no users


   QUERY (online)
   ──────────────
   question
      │
      ├╌╌ ROUTE / GUARD ╌╌╌╌╌╌╌╌╌╌╌╌ decide where, or whether, to search
      │     ├╌ Router retrieval .................. 🧪 [H] stale: old file names
      │     ├╌ Adaptive retrieval ................ ⬜
      │     ├╌ Conversational query rewriting .... ⬜ query.py has no chat
      │     │                                         history yet
      │     ├╌ Federated retrieval ............... ⬜ when the HR database
      │     │                                         joins the policies
      │     └╌ Authorisation · injection guards .. ✗ trusted text, no users
      │
      ├╌╌ TRANSFORM THE QUESTION
      │     ├╌ Query rewriting ................... 🧪 [A]
      │     ├╌ Multi-query (+ merge) ............. 🧪 [B]
      │     ├╌ Self-query (question → filter) .... ⏭ after hybrid search
      │     ├╌ Query decomposition ............... ⬜
      │     ├╌ Query normalization ............... ⬜
      │     ├╌ Query expansion (keywords) ........ ⬜
      │     ├╌ HyDE · Step-back prompting ........ ⬜
      │     └╌ Query translation ................. ✗ English only
      ▼
   RETRIEVE
      │     ├╌ Dense retrieval ................... ✅
      │     ├╌ Sparse: BM25 · Full-text .......... ⬜ only as part of hybrid
      │     ├╌ Hybrid: dense + sparse/BM25 ....... ⏭ next ([D] basic-rag)
      │     ├╌ Metadata-filtered · Faceted ....... 🧪 [C] basic-rag, one
      │     │                                         question
      │     ├╌ Hierarchical · Parent-child ....... ⬜
      │     ├╌ Multi-hop ......................... ⬜
      │     ├╌ Time-aware ........................ ✗ one version per policy
      │     └╌ Graph-based · Graph RAG ........... ✗ no entity links needed
      ▼
   FUSE (only when several result lists)
      │     ├╌ Reciprocal Rank Fusion (RRF) ...... ⏭ with hybrid ([D] k=60)
      │     ├╌ Deduplication ..................... 🧪 inside [B]
      │     └╌ Weighted score fusion · DBSF ...... ⬜
      ▼
   RERANK
      │     ├╌ Cross-encoder: BGE v2-m3, 10 → 3 .. 🧪 [E] best so far; on
      │     │                                         with --rerank
      │     ├╌ FlashRank ......................... ⬜
      │     ├╌ LLM-based reranking ............... ⬜
      │     ├╌ Cohere Reranker ................... ✗ paid API, we run local
      │     └╌ ColBERT · Learning-to-Rank ........ ✗ 370 chunks / too few
      │                                             labels
      ▼
   REFINE (what reaches the prompt)
      │     ├╌ Top-K selection (3) ............... ✅
      │     ├╌ Reranker score threshold .......... ⬜
      │     ├╌ Similarity threshold .............. ⬜
      │     ├╌ MMR · Diversity · Deduplication ... ⬜
      │     ├╌ Parent document expansion ......... ⬜
      │     └╌ Contextual compression ............ 🧪 [G] basic-rag
      ▼
   PROMPT + GENERATE
      │     ├╌ Grounding rules (answer only from
      │     │  context, say "can't tell") ........ ✅ rules are leave-centric:
      │     │                                         refresh ⏭
      │     ├╌ Labelled context (file name) ...... ✅
      │     ├╌ Self-check before answering ....... ✅ rule 8
      │     ├╌ Claim-level citations ............. ⏭
      │     ├╌ Structured output (schema) ........ ⬜ (the judge uses it ✅)
      │     └╌ Lost in the middle ordering ....... ✗ only 3 chunks
      ▼
   VERIFY
      │     ├╌ Citation validation ............... ⬜
      │     ├╌ Faithfulness / entailment check ... ⬜
      │     ├╌ Corrective RAG (CRAG) ............. ⬜ LangGraph
      │     ├╌ Iterative · Recursive retrieval ... ⬜ LangGraph
      │     └╌ Self-RAG · Agentic retrieval ...... ⬜ LangGraph
      ▼
   answer


   MEASURE
   ───────
   top chunks ══ Hit Rate · Recall · MRR ............ ✅ evaluate_retrieval.py
             ══ Latency (ms per question) ........... 🧪 reranker comparison
             ══ Precision@K ......................... ⬜
             ══ MAP · nDCG .......................... ✗ labels are yes/no
   answer ═════ LLM judge: correctness ·
                context support (= faithfulness) ·
                completeness ........................ ✅ evaluate_answers.py
             ══ Judge checked against a human ....... ⬜
             ══ Dev / test split .................... ⬜ column exists, unused
   every run ══ Regression test / release gate ...... ⏭
             ══ Tracing (LangSmith) ................. ⬜
             ══ Cost ................................ ✗ all local: time is
                                                        the cost
```

### When to use what

Each note: the symptom that calls for it, and an example. Skipped (✗)
techniques are left out; their reason is in the map.

**Load / parse**
- **PDF / Word / HTML loaders, OCR**: the sources stop being plain
  text. A scanned PDF has no text layer at all, so it needs OCR first.

**Chunk**
- **Structure-aware**: the documents have headings. One section, one
  rule: "6.4 Parking in Austin" stays whole instead of being cut.
- **Contextual chunk header**: a chunk makes no sense on its own. "Up
  to 5 unused annual-leave days" doesn't say for which country until
  the header adds "Chapter 4: Employee Leave Policy (India)".
- **Contextual retrieval**: the header isn't enough, and an LLM can
  write one sentence of context per chunk before embedding. Costs one
  LLM call per chunk at ingestion.
- **Semantic chunking**: there are no headings, so cut where the topic
  changes (where neighbouring sentences' embeddings drift apart).
- **Parent-child chunks**: small chunks match well but answer badly.
  Search a sentence-sized child, hand the LLM its whole section.

**Metadata**
- **Fields that can be filtered on**: a question names something a
  chunk can be tagged with. "Austin" → country = US.
- **Stable chunk IDs**: ingestion updates the collection instead of
  rebuilding it, so the same chunk must keep the same ID and not be
  stored twice.

**Embed**
- **Dense + prefixes**: always the base. The model's prefixes
  (`search_document:` / `search_query:`) are part of how it was trained.
- **Sparse vectors**: exact words matter: IDs, codes, names. Needed for
  hybrid search.

**Index**
- **Payload index**: filters are used on a large collection; index the
  field you filter on so the filter stays fast.

**Route / guard**
- **Router retrieval**: questions belong to clearly separate areas.
  "the vendor hasn't been paid" → Finance only.
- **Adaptive retrieval**: some messages need no search. "thanks!"
  shouldn't fetch three chunks.
- **Conversational query rewriting**: there is chat history. "and in
  Pune?" after a leave question → "How many leave days in Pune?"
- **Federated retrieval**: answers live in more than one system, e.g.
  the policies plus the HR database.

**Transform the question**
- **Query rewriting**: questions are casual or vague. "hey when do i
  get paid" → "When is salary paid?"
- **Multi-query**: one phrasing misses; search three and merge.
- **Self-query**: the question carries a filter value. "casual leave
  in Austin" → search with country = US.
- **Query decomposition**: one question needs two sections. "Do I get
  more leave in Pune or Austin?" → one search per office.
- **Query normalization**: users write abbreviations or typos the
  documents don't. "WFH" → "work from home".
- **Query expansion (keywords)**: users and documents use different
  words. "sick day" → also "medical leave".
- **HyDE**: questions are short and the documents formal. Embed a
  made-up answer, which looks more like a policy than the question
  does.
- **Step-back prompting**: the answer needs a general rule first.
  "Can I carry over 7 days?" → also fetch "carry-over rules".

**Retrieve**
- **Dense retrieval**: always the base: finds meaning. "time off"
  finds "annual leave".
- **Sparse / BM25 / full-text alone**: people search with exact
  keywords, like a search box. Rarely enough on its own for questions.
- **Hybrid search**: dense misses exact terms. "IT-AUP-2026" means
  little as a vector; BM25 matches it exactly.
- **Metadata-filtered / faceted**: results come from the wrong office
  or department. Several filters at once is faceted (country + dept).
- **Hierarchical / parent-child**: questions range from "what does
  chapter 4 cover?" to one exact rule; search at the matching level.
- **Multi-hop**: the first result points somewhere else. "see section
  6.2" → fetch 6.2 too.

**Fuse**
- **RRF**: two or more ranked lists (dense + BM25, or several
  queries). Uses ranks, not scores, so different scales don't matter.
- **Deduplication**: the same chunk comes back from several searches.
- **Weighted fusion / DBSF**: one list should count more than the
  other, and its scores are worth trusting.

**Rerank**
- **Cross-encoder**: the right chunk is in the top 10 but not the top
  3. Reads question and chunk together; slower, so only on candidates.
- **FlashRank**: the cross-encoder is too slow; smaller and faster,
  usually a little less accurate.
- **LLM-based reranking**: the cross-encoder still orders badly.
  Slowest: one LLM call per candidate.

**Refine**
- **Top-K**: always. How many chunks the LLM gets.
- **Reranker / similarity threshold**: weak chunks get in. If the best
  score is low, say "I can't tell" instead of answering from noise.
- **MMR / diversity / dedup**: the top 3 say the same thing (a fact
  repeated in two chapters), crowding out a second needed section.
- **Parent document expansion**: the chunk found is right but too
  small to answer from.
- **Contextual compression**: chunks are long and mostly irrelevant;
  keep only the sentences that matter.

**Prompt + generate**
- **Grounding rules**: always. Answer only from the context; say "I
  can't tell" when it doesn't.
- **Labelled context**: similar rules from different documents get
  mixed up. The label shows which is India's and which is the US's.
- **Claim-level citations**: answers mix up chunks. "Parking is free in
  the building garage [Facilities 6.4]" can be checked.
- **Structured output**: the answer feeds code (citations, scores),
  not just a human.

**Verify**
- **Citation validation**: citations exist and must be checked. Does
  6.4 really say that, and is it the office asked about (6.4 is
  Austin, not Pune)?
- **Faithfulness check**: the model adds things not in the chunks,
  e.g. invented visitor rules. Drop unsupported claims.
- **CRAG**: retrieval is sometimes weak. Grade the chunks; if poor,
  rewrite and search again, or say "I can't tell".
- **Iterative / recursive**: one search isn't enough, or a chunk
  refers to another section.
- **Self-RAG / agentic**: the model should decide itself when to
  search and with which tool. The most flexible, and the hardest to
  test.

**Measure**
- **Hit Rate, Recall, MRR**: always, before scoring answers.
- **Precision@K**: you want to know how much noise the LLM sees.
- **Latency**: a new step adds model calls (rerankers, LLM rewrites).
- **LLM judge**: always for answers. **Check it against a human** on
  ~20 answers before trusting a 1–2% change.
- **Dev / test split**: tune on dev, report on test, so the final
  number isn't one you tuned for.
- **Regression test / release gate**: every new technique must keep
  the baseline, e.g. Hit Rate ≥ 96.2%, or it isn't promoted.
- **Tracing**: you need to see why one question failed without
  re-running a script.
