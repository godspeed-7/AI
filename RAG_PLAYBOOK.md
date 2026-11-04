# RAG Playbook

A quick guide: every RAG option, by pipeline step. The overview shows
what exists at each step; the sections below say in one line when to
use each one, and what happened when we tried it.

- A technique any RAG system could use → **this file**.
- How our code does it → that project's README or `PIPELINE_FLOW.md`.

**Status**, in the step sections (for ams-assistant):
✅ in use · ⏭ next · 🧪 tried, waiting to be promoted ·
⬜ not tried · ✗ skipped or failed

**Data**: v1 = the old 10 policy docs (133 questions). v2 = the 6
handbooks (263 questions), from 3 Nov 2026. Their scores don't compare.

---

## Overview

```text
   INGESTION (run again when documents, chunking or embedding change)

   handbooks (.txt)
      │
      ▼
   1 LOAD
      │
      ├╌╌ Loaders
      │     ├╌ plain text
      │     ├╌ PDF · Word · HTML
      │     └╌ OCR (scanned pages)
      ├╌╌ Cleaning
      │     └╌ strip headers, footers, page numbers
      ▼
   2 CHUNK
      │
      ├╌╌ Types of chunking
      │     ├╌ fixed-size (+ overlap)
      │     ├╌ sentence / paragraph
      │     ├╌ recursive
      │     ├╌ by section (structure-aware)
      │     ├╌ semantic
      │     └╌ hierarchical: parent-child · RAPTOR
      ├╌╌ Add context to each chunk
      │     ├╌ chunk header (breadcrumb)
      │     └╌ contextual retrieval (LLM-written line)
      ▼
   3 METADATA
      │
      ├╌╌ Fields
      │     ├╌ descriptive: source · department · chapter · section
      │     └╌ filter: values a search can narrow by (country, year)
      ├╌╌ Identity
      │     └╌ stable chunk IDs
      ├╌╌ Enrichment (an LLM, at ingestion)
      │     ├╌ keywords / synonyms
      │     └╌ entities + links (graph)
      ▼
   4 EMBED
      │
      ├╌╌ Vector types
      │     ├╌ dense
      │     ├╌ sparse (BM25 / SPLADE)
      │     └╌ multi-vector (ColBERT)
      ├╌╌ What gets embedded
      │     ├╌ the chunk (+ document / query prefixes)
      │     ├╌ hypothetical questions per chunk
      │     └╌ a summary per chunk
      ├╌╌ Model
      │     ├╌ pick a model
      │     └╌ fine-tune it on our question → section pairs
      ▼
   5 INDEX
      │
      ├╌╌ Search method
      │     ├╌ exact (brute force)
      │     └╌ approximate: HNSW · IVF
      ├╌╌ Similarity
      │     └╌ cosine · dot product · Euclidean · Manhattan
      ├╌╌ Scale and access
      │     ├╌ quantization
      │     ├╌ payload index
      │     └╌ multi-tenancy
      ▼
   searchable collection


   QUERY (every question)

   question
      │
      ▼
   6 ROUTE
      │
      ├╌╌ Choose where to search
      │     ├╌ router (pick documents or departments)
      │     └╌ intent routing (policy · small talk · HR database)
      ├╌╌ Choose whether to search
      │     ├╌ adaptive retrieval
      │     └╌ semantic cache (answered before?)
      ├╌╌ Guard
      │     └╌ permissions · treat retrieved text as untrusted
      ▼
   7 TRANSFORM
      │
      ├╌╌ Clean up the question
      │     ├╌ rewriting · normalization · translation
      │     └╌ conversational (uses chat history)
      ├╌╌ Search with more than one query
      │     ├╌ multi-query · keyword expansion
      │     ├╌ decomposition · step-back
      │     └╌ HyDE (a made-up answer)
      ├╌╌ Turn the question into a filter
      │     └╌ self-query
      ▼
   8 RETRIEVE
      │
      ├╌╌ Search type
      │     ├╌ dense
      │     ├╌ sparse (BM25 / full-text)
      │     └╌ hybrid (dense + sparse)
      ├╌╌ Narrow the search
      │     ├╌ metadata filter · faceted
      │     └╌ time-aware
      ├╌╌ Search at the right level
      │     └╌ hierarchical · parent-child
      ├╌╌ Follow links or sources
      │     ├╌ multi-hop
      │     ├╌ federated (several systems)
      │     └╌ graph RAG
      ▼
   9 FUSE (only with two or more result lists)
      │
      ├╌╌ Merge rankings
      │     ├╌ RRF (by rank)
      │     └╌ weighted fusion · DBSF (by score)
      ├╌╌ Clean up
      │     └╌ deduplication
      ▼
   10 RERANK
      │
      ├╌╌ Reranker models
      │     ├╌ cross-encoder: BGE reranker · FlashRank
      │     ├╌ late interaction: ColBERT
      │     └╌ hosted: Cohere
      ├╌╌ LLM reranking
      │     └╌ the LLM scores each candidate
      ├╌╌ Learned ranking
      │     └╌ learning-to-rank
      ▼
   11 REFINE
      │
      ├╌╌ How many chunks
      │     ├╌ top-K
      │     └╌ thresholds: similarity · reranker score
      ├╌╌ Variety
      │     └╌ MMR · diversity · deduplication
      ├╌╌ Size of each chunk
      │     ├╌ parent document expansion
      │     └╌ contextual compression
      ▼
   12 GENERATE
      │
      ├╌╌ Prompt rules
      │     ├╌ grounding · abstain ("I can't tell")
      │     └╌ self-check
      ├╌╌ Context layout
      │     ├╌ labelled context
      │     └╌ lost-in-the-middle ordering
      ├╌╌ Output
      │     ├╌ claim-level citations
      │     ├╌ structured output
      │     └╌ streaming
      ▼
   13 VERIFY
      │
      ├╌╌ Check the answer
      │     ├╌ citation check
      │     └╌ faithfulness / entailment
      ├╌╌ Loop back
      │     ├╌ CRAG
      │     ├╌ iterative · recursive
      │     └╌ Self-RAG · agentic
      ▼
   answer


   MEASURE (across both pipelines)

   14 MEASURE
      │
      ├╌╌ Retrieval
      │     ├╌ Hit Rate · Recall · MRR · Precision@K
      │     └╌ MAP · NDCG
      ├╌╌ Answer
      │     ├╌ LLM judge
      │     └╌ judge checked against a human
      ├╌╌ Process
      │     ├╌ dev / test split · regression gate
      │     ├╌ latency · cost
      │     └╌ tracing · feedback loop
      ▼
   scores
```

**Where we stand (v2)**
- Retrieval, top 3: **92.4%** Hit Rate · with the reranker **96.6%**
- Answers: **94.6%** (no reranker). 98% when retrieval hit, 53% when
  it missed: retrieval is still the biggest lever.

---

## 1. Load

Read each file into text; keep the file name as the source.

```text
   handbooks (.txt)
      │
      ▼
   1 LOAD
      │
      ├╌╌ ✅ Plain-text loader ╌╌ every source is .txt
      ├╌╌ ✗  PDF / Word / HTML ╌╌ sources stop being plain text
      ├╌╌ ✗  OCR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ scanned pages with no text layer
      ├╌╌ ✗  Cleaning ╌╌╌╌╌╌╌╌╌╌╌ parsers leave headers, footers, page numbers
      ▼
   text
```

## 2. Chunk

Cut each document into the pieces that get one vector each.

```text
   text
      │
      ▼
   2 CHUNK
      │
      ├╌╌ ✅ By section ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ docs have headings; one section = one
      │                                rule
      ├╌╌ ✅ Chunk header ╌╌╌╌╌╌╌╌╌╌╌╌ the chunk doesn't name its topic: "5
      │                                unused days" + "Chapter 4: Employee
      │                                Leave Policy (India)"
      ├╌╌ ⬜ Semantic ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ no headings; cut where the topic changes
      ├╌╌ ⬜ Parent-child ╌╌╌╌╌╌╌╌╌╌╌╌ small chunks match well but answer badly
      ├╌╌ ⬜ Contextual retrieval ╌╌╌╌ the header isn't enough; an LLM writes
      │                                one line of context per chunk
      ├╌╌ ✗  Fixed-size / recursive ╌╌ cuts rules in half; we have headings
      ├╌╌ ✗  RAPTOR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a tree of summaries for very long
      │                                documents
      ▼
   chunks
```

**Tried**: v1, fixed-size 78.9% → by section 89.5% → + title line and
prefixes 92.5%

## 3. Metadata

Fields stored with each chunk, for citations and filters.

```text
   chunks
      │
      ▼
   3 METADATA
      │
      ├╌╌ ✅ Payload fields ╌╌╌╌╌╌ department, handbook, chapter, section …
      ├╌╌ ⬜ Filter fields ╌╌╌╌╌╌╌ tag chunks with values a search can filter
      │                            on (e.g. country); only useful with
      │                            self-query or a metadata filter (steps 7–8)
      ├╌╌ ⬜ Stable chunk IDs ╌╌╌╌ update the collection instead of rebuilding
      │                            it
      ├╌╌ ⬜ Keyword enrichment ╌╌ users and docs use different words: add
      │                            "freelance, side job" to legal 2.3.2
      │                            "Outside work"
      ├╌╌ ⬜ Entity graph ╌╌╌╌╌╌╌╌ answers need links (who approves what)
      ▼
   chunks + payload
```

## 4. Embed

Turn each chunk into a vector, with the same model as the question.

```text
   chunks
      │
      ▼
   4 EMBED
      │
      ├╌╌ ✅ Dense + prefixes ╌╌╌╌╌╌╌╌ always the base; nomic embeds chunks as
      │                                search_document:, questions as
      │                                search_query:
      ├╌╌ ⏭ Sparse (BM25) ╌╌╌╌╌╌╌╌╌╌╌ exact words matter: "IT-AUP-2026",
      │                                "Journalists'"
      ├╌╌ ⬜ Hypothetical questions ╌╌ users ask casually, docs are formal:
      │                                "How do I move to a different team?" for
      │                                13.5.3; HyDE in reverse, done once at
      │                                ingestion
      ├╌╌ ⬜ Summary per chunk ╌╌╌╌╌╌╌ search a short summary, hand over the
      │                                full chunk
      ├╌╌ ⬜ Other / fine-tuned ╌╌╌╌╌╌ the model misses our domain; means
      │                                re-embedding everything
      ├╌╌ ✗  Multi-vector / ColBERT ╌╌ big collections; we have 370
      ▼
   vectors
```

**Tried**: basic-rag v1, all-minilm → nomic: 89.5% → 93.2%

## 5. Index

Where vectors live and how the nearest are found.

```text
   vectors
      │
      ▼
   5 INDEX
      │
      ├╌╌ ✅ Exact scan, cosine ╌╌ fine up to tens of thousands of chunks
      ├╌╌ ⬜ Payload index ╌╌╌╌╌╌╌ filters on a large collection
      ├╌╌ ✗  HNSW / IVF ╌╌╌╌╌╌╌╌╌╌ a full scan is too slow (Qdrant switches
      │                            itself)
      ├╌╌ ✗  Quantization ╌╌╌╌╌╌╌╌ the index doesn't fit in memory
      ├╌╌ ✗  Multi-tenancy ╌╌╌╌╌╌╌ users must not see each other's chunks
      ▼
   searchable collection
```

## 6. Route

Decide where to search, or whether to search at all.

```text
   question
      │
      ▼
   6 ROUTE
      │
      ├╌╌ ⬜ Adaptive ╌╌╌╌╌╌╌╌╌ some messages need no search ("thanks!")
      ├╌╌ ⬜ Semantic cache ╌╌╌ the same questions keep coming back
      ├╌╌ ⬜ Intent routing ╌╌╌ policy vs small talk vs HR database (LangGraph)
      ├╌╌ ✗  Router ╌╌╌╌╌╌╌╌╌╌╌ an LLM picks documents; adds 1–2 s, about
      │                         quality, not speed
      ├╌╌ ✗  Security guards ╌╌ untrusted docs or many users
      ▼
   where to search
```

**Tried**: v1, router 92.5% → 78.2% (never said "all"); retry when the
data is much larger

## 7. Transform

Change the search text before it's embedded.

```text
   question
      │
      ▼
   7 TRANSFORM
      │
      ├╌╌ ⬜ Decomposition ╌╌╌╌╌╌ "Pune or Austin?" → one search per office
      ├╌╌ ⬜ Normalization ╌╌╌╌╌╌ "WFH" → "work from home"
      ├╌╌ ⬜ Keyword expansion ╌╌ "sick day" → also "medical leave"
      ├╌╌ ⬜ HyDE ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ embed a made-up answer instead of the short
      │                           question
      ├╌╌ ⬜ Step-back ╌╌╌╌╌╌╌╌╌╌ also fetch the general rule
      ├╌╌ ⬜ Conversational ╌╌╌╌╌ "and in Pune?" needs chat history
      ├╌╌ ✗  Rewriting ╌╌╌╌╌╌╌╌╌╌ gemma drifts from the meaning
      ├╌╌ ✗  Multi-query ╌╌╌╌╌╌╌╌ search 3 phrasings and merge
      ├╌╌ ✗  Self-query ╌╌╌╌╌╌╌╌╌ "in Austin" → filter country = US
      ├╌╌ ✗  Translation ╌╌╌╌╌╌╌╌ English only
      ▼
   search text
```

**Tried**
- v1, rewriting: 92.5% → 85.0%; fixed prompt ±0
- v1, multi-query: −0.75%, 120× slower
- v2, rewriting + reranker: 96.6% → 91.3% (2 fixed, 16 broken)
- v2, self-query: would fix ~1 of the 9 remaining misses; skipped

## 8. Retrieve

Find the nearest chunks.

```text
   search text
      │
      ▼
   8 RETRIEVE
      │
      ├╌╌ ✅ Dense, top 3 ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ always the base; finds meaning
      ├╌╌ ⏭ Hybrid (dense + BM25) ╌╌╌╌╌╌╌╌ dense misses exact terms
      ├╌╌ ⬜ Metadata filter / faceted ╌╌╌╌ results from the wrong office or
      │                                     department
      ├╌╌ ⬜ Parent-child / hierarchical ╌╌ search small, answer with more
      ├╌╌ ⬜ Multi-hop ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a chunk says "see section 6.2"
      ├╌╌ ⬜ Federated ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ policies + HR database (agents
      │                                     stage)
      ├╌╌ ✗  Time-aware ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ several versions of a policy
      ├╌╌ ✗  Graph RAG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ answers need entity links
      ▼
   candidate chunks
```

**Tried**: v1, the right chunk was in the top 3, 5 and 10 for 92.5%,
95.5% and 97.7% → a ranking problem → reranking

## 9. Fuse

Merge two or more result lists.

```text
   two or more lists
      │
      ▼
   9 FUSE
      │
      ├╌╌ ⏭ RRF ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ hybrid or multi-query; uses ranks, not
      │                                scores
      ├╌╌ ⬜ Weighted fusion / DBSF ╌╌ one list should count more
      ├╌╌ ⬜ Deduplication ╌╌╌╌╌╌╌╌╌╌╌ the same chunk from several searches
      ▼
   one list
```

## 10. Rerank

Fetch more, score again with question + chunk together, keep the best.

```text
   10 candidates
      │
      ▼
   10 RERANK
      │
      ├╌╌ 🧪 BGE reranker v2-m3 ╌╌╌╌╌╌╌╌╌╌ the right chunk is in the top 10,
      │                                    not the top 3; on with --rerank,
      │                                    promote after the answer eval
      ├╌╌ ⬜ FlashRank ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ the reranker is too slow
      ├╌╌ ⬜ LLM reranker ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ the cross-encoder still orders badly
      ├╌╌ ✗  Cohere ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ paid API; we run local
      ├╌╌ ✗  ColBERT / learning-to-rank ╌╌ big collections, many labels
      ▼
   top 3
```

**Tried**: v2, 10 → 3: none 92.4% · base 95.4% (0.24s) · v2-m3 96.6%
(0.85s)

**Watch out**: when every score is near 0, the order is noise

## 11. Refine

Decide what reaches the prompt.

```text
   ranked chunks
      │
      ▼
   11 REFINE
      │
      ├╌╌ ✅ Top-K = 3 ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ K = 5 gave no better answers
      │                                  (basic-rag)
      ├╌╌ ⬜ Reranker score threshold ╌╌ weak chunks get in
      ├╌╌ ⬜ Diversity / dedup ╌╌╌╌╌╌╌╌╌ the top 3 repeat the same fact
      ├╌╌ ⬜ Parent expansion ╌╌╌╌╌╌╌╌╌╌ the right chunk is too small to answer
      │                                  from
      ├╌╌ ⬜ Compression ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ chunks are long and mostly irrelevant
      ├╌╌ ✗  Similarity threshold ╌╌╌╌╌╌ no clean cut-off (v1)
      ├╌╌ ✗  MMR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ pushed out good chunks (v1)
      ▼
   chunks for the prompt
```

## 12. Generate

Prompt the model with the chunks and the question.

```text
   chunks + question
      │
      ▼
   12 GENERATE
      │
      ├╌╌ ✅ Grounding rules ╌╌╌╌╌╌╌╌ answer only from context, else "I can't
      │                               tell"
      ├╌╌ ✅ Labelled context ╌╌╌╌╌╌╌ tells India's rule from the US one
      ├╌╌ ✅ Self-check ╌╌╌╌╌╌╌╌╌╌╌╌╌ the model re-reads before answering
      ├╌╌ ⏭ Claim-level citations ╌╌ "free in the garage [Facilities 6.4]"
      ├╌╌ ⏭ Prompt refresh ╌╌╌╌╌╌╌╌╌ the rules are still leave-centric
      ├╌╌ ⬜ Structured output ╌╌╌╌╌╌ the answer feeds code
      ├╌╌ ⬜ Streaming ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ the first words show at once
      ├╌╌ ✗  Lost in the middle ╌╌╌╌╌ matters with many chunks; we send 3
      ▼
   answer
```

**Tried**: v2, 9 wrong answers had the right chunk (payroll vs office,
invented visitor rules) → citations + faithfulness check

## 13. Verify

Check the answer before returning it; loop back if it's weak.

```text
   answer
      │
      ▼
   13 VERIFY
      │
      ├╌╌ ⬜ Citation check ╌╌╌╌╌╌╌╌╌ does 6.4 really say that, for that
      │                               office?
      ├╌╌ ⬜ Faithfulness ╌╌╌╌╌╌╌╌╌╌╌ drop claims the chunks don't support
      ├╌╌ ⬜ CRAG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ grade the chunks; if poor, search again
      │                               (LangGraph)
      ├╌╌ ⬜ Iterative / recursive ╌╌ one search isn't enough
      ├╌╌ ⬜ Self-RAG / agentic ╌╌╌╌╌ the model decides when and how to search
      ▼
   checked answer
```

## 14. Measure

Score the chunks first, then the answer.

```text
   top chunks · answer
      │
      ▼
   14 MEASURE
      │
      ├╌╌ ✅ Hit Rate · Recall · MRR ╌╌ did the right section come back, and
      │                                 how high?
      ├╌╌ ✅ LLM judge ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ correctness · context support ·
      │                                 completeness
      ├╌╌ ⏭ Regression gate ╌╌╌╌╌╌╌╌╌╌ no promotion below the baseline
      ├╌╌ 🧪 Latency ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ every step that adds a model call
      ├╌╌ ⬜ Precision@K ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ how much noise the LLM sees
      ├╌╌ ⬜ Judge vs human ╌╌╌╌╌╌╌╌╌╌╌ check ~20 answers before trusting 1–2%
      ├╌╌ ⬜ Dev / test split ╌╌╌╌╌╌╌╌╌ tune on one, report on the other
      ├╌╌ ⬜ Tracing ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ see why one question failed
      ├╌╌ ✗  MAP / NDCG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ need graded labels; ours are yes/no
      ▼
   scores
```

**Rules**: a 1–2% swing is judge noise. Fix the labels before the
pipeline (also_correct: 87.8% → 92.4% with no code change)

---

## How to try a technique

```text
 1. Experiment  change ONE step (re-ingest first if it's steps 1–5)
 2. Compare     same questions, same scoring, against the baseline
 3. Decide      clearly better and worth the time? If not, stop here
 4. Record      a "Tried" line + status here, win or lose
 5. Promote     move it into the pipeline; re-run evals = new baseline
```

---

## Appendix: catalogue → step

1. **Query transformation** → 7
2. **Retrieval** → 4 (dense, sparse, multi-vector, ColBERT),
   5 (exact, ANN, HNSW, IVF, multi-tenancy), 8 (the rest)
3. **Result fusion** → 9
4. **Reranking** → 10
5. **Retrieval refinement** → 11
6. **Advanced architectures** → 2 (RAPTOR), 6 (router, adaptive),
   7 (self-query), 8 (graph RAG), 13 (CRAG, Self-RAG, agentic,
   iterative, recursive)
7. **Retrieval evaluation** → 14

**Beyond the catalogue**: chunking (2), hypothetical questions and
summaries (4), keyword enrichment (3), generation (12), verification
(13), judge, tracing and gates (14).
