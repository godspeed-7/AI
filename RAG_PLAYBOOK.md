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
handbooks (266 answerable questions; 263 until 7 Nov 2026), from 3 Nov
2026. Their scores don't compare.

---

## Overview

**Jump to** · Ingestion: [1 Load](#1-load) · [2 Chunk](#2-chunk) ·
[3 Metadata](#3-metadata) · [4 Embed](#4-embed) · [5 Index](#5-index)
· Query: [6 Route](#6-route) · [7 Transform](#7-transform) ·
[8 Retrieve](#8-retrieve) · [9 Fuse](#9-fuse) · [10 Rerank](#10-rerank)
· [11 Refine](#11-refine) · [12 Generate](#12-generate) ·
[13 Verify](#13-verify) · [14 Measure](#14-measure)

```text
   🟧 INGESTION (run again when documents, chunking or embedding change)

   handbooks (.txt)
      │
      ▼
   🟦 1 LOAD
      │
      ├╌╌ 🟢 Loaders
      │     ├╌ plain text
      │     ├╌ PDF · Word · HTML
      │     └╌ OCR (scanned pages)
      ├╌╌ 🟢 Cleaning
      │     └╌ strip headers, footers, page numbers
      ▼
   🟦 2 CHUNK
      │
      ├╌╌ 🟢 Types of chunking
      │     ├╌ fixed-size (+ overlap)
      │     ├╌ sentence / paragraph
      │     ├╌ recursive
      │     ├╌ by section (structure-aware)
      │     ├╌ semantic
      │     └╌ hierarchical: parent-child · RAPTOR
      ├╌╌ 🟢 Add context to each chunk
      │     ├╌ chunk header (breadcrumb)
      │     └╌ contextual retrieval (LLM-written line)
      ▼
   🟦 3 METADATA
      │
      ├╌╌ 🟢 Fields
      │     ├╌ descriptive: source · department · chapter · section
      │     └╌ filter: values a search can narrow by (country, year)
      ├╌╌ 🟢 Identity
      │     └╌ stable chunk IDs
      ├╌╌ 🟢 Enrichment (at ingestion)
      │     ├╌ keywords / synonyms (an LLM, from the chunk)
      │     ├╌ glossary rules (hand-written, no LLM)
      │     └╌ entities + links (graph)
      ▼
   🟦 4 EMBED
      │
      ├╌╌ 🟢 Vector types
      │     ├╌ dense
      │     ├╌ sparse (BM25 / SPLADE)
      │     └╌ multi-vector (ColBERT)
      ├╌╌ 🟢 What gets embedded
      │     ├╌ the chunk (+ document / query prefixes)
      │     ├╌ hypothetical questions per chunk
      │     └╌ a summary per chunk
      ├╌╌ 🟢 Model
      │     ├╌ pick a model
      │     └╌ fine-tune it on our question → section pairs
      ▼
   🟦 5 INDEX
      │
      ├╌╌ 🟢 Search method
      │     ├╌ exact (brute force)
      │     └╌ approximate: HNSW · IVF
      ├╌╌ 🟢 Similarity
      │     └╌ cosine · dot product · Euclidean · Manhattan
      ├╌╌ 🟢 Scale and access
      │     ├╌ quantization
      │     ├╌ payload index
      │     └╌ multi-tenancy
      ▼
   searchable collection


   🟧 QUERY (every question)

   question
      │
      ▼
   🟦 6 ROUTE
      │
      ├╌╌ 🟢 Choose where to search
      │     ├╌ router (pick documents or departments)
      │     └╌ intent routing (policy · small talk · HR database)
      ├╌╌ 🟢 Choose whether to search
      │     ├╌ adaptive retrieval
      │     └╌ semantic cache (answered before?)
      ├╌╌ 🟢 Guard
      │     └╌ permissions · treat retrieved text as untrusted
      ▼
   🟦 7 TRANSFORM
      │
      ├╌╌ 🟢 Clean up the question
      │     ├╌ rewriting · normalization · translation
      │     └╌ conversational (uses chat history)
      ├╌╌ 🟢 Search with more than one query
      │     ├╌ multi-query · keyword expansion
      │     │  (from an LLM or a glossary)
      │     ├╌ decomposition · step-back
      │     └╌ HyDE (a made-up answer)
      ├╌╌ 🟢 Turn the question into a filter
      │     └╌ self-query
      ▼
   🟦 8 RETRIEVE
      │
      ├╌╌ 🟢 Search type
      │     ├╌ dense
      │     ├╌ sparse (BM25 / full-text)
      │     └╌ hybrid (dense + sparse)
      ├╌╌ 🟢 Narrow the search
      │     ├╌ metadata filter · faceted
      │     └╌ time-aware
      ├╌╌ 🟢 Search at the right level
      │     └╌ hierarchical · parent-child
      ├╌╌ 🟢 Follow links or sources
      │     ├╌ multi-hop
      │     ├╌ federated (several systems)
      │     └╌ graph RAG
      ▼
   🟦 9 FUSE (only with two or more result lists)
      │
      ├╌╌ 🟢 Merge rankings
      │     ├╌ RRF (by rank)
      │     └╌ weighted fusion · DBSF (by score)
      ├╌╌ 🟢 Clean up
      │     └╌ deduplication
      ▼
   🟦 10 RERANK
      │
      ├╌╌ 🟢 Reranker models
      │     ├╌ cross-encoder: BGE reranker · FlashRank
      │     ├╌ late interaction: ColBERT
      │     └╌ hosted: Cohere
      ├╌╌ 🟢 LLM reranking
      │     └╌ the LLM scores each candidate
      ├╌╌ 🟢 Learned ranking
      │     └╌ learning-to-rank
      ▼
   🟦 11 REFINE
      │
      ├╌╌ 🟢 How many chunks
      │     ├╌ top-K
      │     └╌ thresholds: similarity · reranker score
      ├╌╌ 🟢 Variety
      │     └╌ MMR · diversity · deduplication
      ├╌╌ 🟢 Size of each chunk
      │     ├╌ parent document expansion
      │     └╌ contextual compression
      ▼
   🟦 12 GENERATE
      │
      ├╌╌ 🟢 Prompt rules
      │     ├╌ grounding · abstain ("I can't tell")
      │     └╌ self-check
      ├╌╌ 🟢 Context layout
      │     ├╌ labelled context
      │     └╌ lost-in-the-middle ordering
      ├╌╌ 🟢 Output
      │     ├╌ claim-level citations
      │     ├╌ structured output
      │     └╌ streaming
      ▼
   🟦 13 VERIFY
      │
      ├╌╌ 🟢 Check the answer
      │     ├╌ citation check
      │     └╌ faithfulness / entailment
      ├╌╌ 🟢 Loop back
      │     ├╌ CRAG
      │     ├╌ iterative · recursive
      │     └╌ Self-RAG · agentic
      ▼
   answer


   🟧 MEASURE (across both pipelines)

   🟦 14 MEASURE
      │
      ├╌╌ 🟢 Retrieval
      │     ├╌ Hit Rate · Recall · MRR · Precision@K
      │     └╌ MAP · NDCG
      ├╌╌ 🟢 Answer
      │     ├╌ LLM judge
      │     └╌ judge checked against a human
      ├╌╌ 🟢 Process
      │     ├╌ dev / test split · regression gate
      │     ├╌ latency · cost
      │     └╌ tracing · feedback loop
      ▼
   scores
```

**Where we stand (v2, 7 Nov 2026)**
- Retrieval, top 3: **92.4%** Hit Rate · with the reranker and glossary
  rules **97.4%** (259 of 266)
- Answers: **88.0%** (194 of 284 perfect), graded by Gemma 4 26B. 76 of
  the 90 imperfect answers had the right chunk: the answer model is now
  the biggest lever.

---

## 1. Load

Read each file into text; keep the file name as the source.

```text
   handbooks (.txt)
      │
      ▼
   1 LOAD
      │
      ├╌╌ ✅ Plain-text loader ╌╌ read .txt files as they are; every source is
      │                           .txt
      ├╌╌ ✗  PDF / Word / HTML ╌╌ pull the text out of other file types,
      │                           keeping headings and tables
      ├╌╌ ✗  OCR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ turn images of text into text: scanned pages
      ├╌╌ ✗  Cleaning ╌╌╌╌╌╌╌╌╌╌╌ strip parser junk: page headers, footers,
      │                           page numbers
      ▼
   text
```

[↑ Overview](#overview)

## 2. Chunk

Cut each document into the pieces that get one vector each.

```text
   text
      │
      ▼
   2 CHUNK
      │
      ├╌╌ ✅ By section ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ one chunk per numbered section: "6.4
      │                                Parking in Austin" stays whole
      ├╌╌ ✅ Chunk header ╌╌╌╌╌╌╌╌╌╌╌╌ put the document and chapter title on
      │                                top of each chunk: "5 unused days" +
      │                                "Chapter 4: Employee Leave Policy
      │                                (India)"
      ├╌╌ 🧪 Contextual retrieval ╌╌╌╌ an LLM reads the whole document and
      │                                writes one line of context per chunk:
      │                                "probation for India (Bengaluru, Pune)
      │                                and US (Austin)"
      ├╌╌ ⬜ Semantic ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ cut where neighbouring sentences change
      │                                topic; for text without headings
      ├╌╌ ⬜ Parent-child ╌╌╌╌╌╌╌╌╌╌╌╌ search small pieces, hand the LLM the
      │                                bigger section they belong to
      ├╌╌ ✗  Fixed-size / recursive ╌╌ cut every N characters (recursive: at
      │                                the nearest paragraph or sentence); cuts
      │                                rules in half when headings exist
      ├╌╌ ✗  RAPTOR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ build a tree of summaries over the
      │                                chunks; for very long documents
      ▼
   chunks
```

**Tried**
- v1, fixed-size 78.9% → by section 89.5% → + title line and prefixes
  92.5%
- v2, contextual retrieval: 97.34% → 97.72% (1 question); kept off

[↑ Overview](#overview)

## 3. Metadata

Fields stored with each chunk, for citations and filters.

```text
   chunks
      │
      ▼
   3 METADATA
      │
      ├╌╌ ✅ Payload fields ╌╌╌╌╌╌ labels stored next to each vector:
      │                            department, handbook, chapter, section …
      ├╌╌ ✅ Glossary rules ╌╌╌╌╌╌ add a fact the chunk can't show, by a
      │                            hand-written rule: says "US payroll" → add
      │                            "Austin office"
      ├╌╌ ⬜ Filter fields ╌╌╌╌╌╌╌ values a search can narrow by: country = US;
      │                            only useful with self-query or a metadata
      │                            filter (steps 7–8)
      ├╌╌ ⬜ Stable chunk IDs ╌╌╌╌ build each ID from the chunk's address
      │                            ("employee_handbook#5.3"), so re-ingest
      │                            updates instead of rebuilding
      ├╌╌ ⬜ Keyword enrichment ╌╌ an LLM reads the chunk and adds the words
      │                            users would use: "freelance, side job" for
      │                            legal 2.3.2 "Outside work"
      ├╌╌ ⬜ Entity graph ╌╌╌╌╌╌╌╌ pull out things and the links between them:
      │                            HR-LEAVE-US-2026 → points to →
      │                            HR-LEAVE-IN-2026
      ▼
   chunks + payload
```

**Tried**: v2 + reranker, glossary rules on the chunks: 96.58% →
97.34% (2 fixed, 0 broken); in use

[↑ Overview](#overview)

## 4. Embed

Turn each chunk into a vector, with the same model as the question.

```text
   chunks
      │
      ▼
   4 EMBED
      │
      ├╌╌ ✅ Dense + prefixes ╌╌╌╌╌╌╌╌ a model turns text into a meaning
      │                                vector; nomic needs search_document: /
      │                                search_query: in front
      ├╌╌ 🧪 Hypothetical questions ╌╌ an LLM writes questions each chunk
      │                                answers; each is its own point pointing
      │                                back to the chunk: "How do I move to a
      │                                different team?" → 13.5
      ├╌╌ ⬜ Summary per chunk ╌╌╌╌╌╌╌ an LLM writes a short summary; search on
      │                                it, hand over the full chunk
      ├╌╌ ⬜ Other / fine-tuned ╌╌╌╌╌╌ swap the model, or train it on our
      │                                question → section pairs; means
      │                                re-embedding everything
      ├╌╌ ✗  Sparse (BM25) ╌╌╌╌╌╌╌╌╌╌╌ a vector of exact word counts: finds
      │                                "IT-AUP-2026", "Journalists'"
      ├╌╌ ✗  Multi-vector / ColBERT ╌╌ one vector per word, compared word by
      │                                word; accurate but heavy, for big
      │                                collections
      ▼
   vectors
```

**Tried**
- basic-rag v1, all-minilm → nomic: 89.5% → 93.2%
- v2, hypothetical questions: 97.34% → 97.72% (1 question); kept off
- v2, BM25 (hand-written, for hybrid search): no gain, see step 8

[↑ Overview](#overview)

## 5. Index

Where vectors live and how the nearest are found.

```text
   vectors
      │
      ▼
   5 INDEX
      │
      ├╌╌ ✅ Exact scan, cosine ╌╌ compare the question with every vector; fine
      │                            up to tens of thousands of chunks
      ├╌╌ ⬜ Payload index ╌╌╌╌╌╌╌ an index on a filter field, so filters stay
      │                            fast on a big collection
      ├╌╌ ✗  HNSW / IVF ╌╌╌╌╌╌╌╌╌╌ skip most vectors (a graph or clusters) to
      │                            search fast; can miss a neighbour; Qdrant
      │                            switches on its own
      ├╌╌ ✗  Quantization ╌╌╌╌╌╌╌╌ store each number in fewer bits to save
      │                            memory; re-check recall
      ├╌╌ ✗  Multi-tenancy ╌╌╌╌╌╌╌ keep each customer's chunks apart with a
      │                            filter applied before search
      ▼
   searchable collection
```

[↑ Overview](#overview)

## 6. Route

Decide where to search, or whether to search at all.

```text
   question
      │
      ▼
   6 ROUTE
      │
      ├╌╌ ⬜ Adaptive ╌╌╌╌╌╌╌╌╌ decide if a message needs a search at all:
      │                         "thanks!" → just reply
      ├╌╌ ⬜ Semantic cache ╌╌╌ reuse the saved answer for a question with the
      │                         same meaning: "what date do we get paid?" ≈
      │                         "when is salary paid?"
      ├╌╌ ⬜ Intent routing ╌╌╌ send each request to the right tool: policy
      │                         search, small talk or the HR database
      │                         (LangGraph)
      ├╌╌ ✗  Router ╌╌╌╌╌╌╌╌╌╌╌ an LLM picks which documents to search: "vendor
      │                         not paid" → Finance only; a wrong pick hides
      │                         the answer
      ├╌╌ ✗  Security guards ╌╌ filter by permission before search; treat
      │                         retrieved text as data, never instructions
      ▼
   where to search
```

**Tried**: v1, router 92.5% → 78.2% (never said "all"); retry when the
data is much larger

[↑ Overview](#overview)

## 7. Transform

Change the search text before it's embedded.

```text
   question
      │
      ▼
   7 TRANSFORM
      │
      ├╌╌ ⬜ Normalization ╌╌╌╌╌╌ fix abbreviations and typos by rule: "WFH" →
      │                           "work from home"
      ├╌╌ ⬜ HyDE ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ an LLM writes a made-up answer; search with
      │                           that instead of the question
      ├╌╌ ⬜ Step-back ╌╌╌╌╌╌╌╌╌╌ also search a broader version: "carry over 7
      │                           days?" → also "carry-over rules"
      ├╌╌ ⬜ Conversational ╌╌╌╌╌ turn a follow-up into a full question using
      │                           chat history: "and in Pune?" → "How many
      │                           leave days in Pune?"
      ├╌╌ ✗  Decomposition ╌╌╌╌╌╌ split a question that needs two answers into
      │                           sub-questions, search each: "Pune or Austin?"
      │                           → one search per office
      ├╌╌ ✗  Keyword expansion ╌╌ add related words to the same query (from an
      │                           LLM or a glossary): "sick day" → also
      │                           "medical leave"
      ├╌╌ ✗  Rewriting ╌╌╌╌╌╌╌╌╌╌ an LLM rewrites the question in clearer
      │                           words: "hey when do i get paid" → "When is
      │                           salary paid?"
      ├╌╌ ✗  Multi-query ╌╌╌╌╌╌╌╌ an LLM writes 2–3 phrasings; search each,
      │                           merge the results
      ├╌╌ ✗  Self-query ╌╌╌╌╌╌╌╌╌ an LLM pulls a filter out of the question:
      │                           "casual leave in Austin" → country = US
      ├╌╌ ✗  Translation ╌╌╌╌╌╌╌╌ translate the question into the documents'
      │                           language
      ▼
   search text
```

**Tried**
- v1, rewriting: 92.5% → 85.0%; fixed prompt ±0
- v1, multi-query: −0.75%, 120× slower
- v2, rewriting + reranker: 96.6% → 91.3% (2 fixed, 16 broken)
- v2, self-query: would fix ~1 of the 9 remaining misses; skipped
- v2, decomposition: 97.34% → 96.58%; gemma split only 12 of 263
  questions, and the halves lost context
- v2, glossary on the question: on top of the chunk side, 1 fixed,
  1 broken; kept off

[↑ Overview](#overview)

## 8. Retrieve

Find the nearest chunks.

```text
   search text
      │
      ▼
   8 RETRIEVE
      │
      ├╌╌ ✅ Dense, top 3 ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ return the chunks whose vectors are
      │                                     closest to the question's: "time
      │                                     off" finds "annual leave"
      ├╌╌ ⬜ Metadata filter / faceted ╌╌╌╌ search only chunks whose fields
      │                                     match (faceted: several fields at
      │                                     once): country = US
      ├╌╌ ⬜ Parent-child / hierarchical ╌╌ search small chunks or summaries,
      │                                     return the bigger section they
      │                                     belong to
      ├╌╌ ⬜ Multi-hop ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ search again with what the first
      │                                     result points to: "see section 6.2"
      │                                     → fetch 6.2
      ├╌╌ ⬜ Federated ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ search several systems and combine:
      │                                     policies + HR database (agents
      │                                     stage)
      ├╌╌ ✗  Hybrid (dense + BM25) ╌╌╌╌╌╌╌╌ run meaning search and keyword
      │                                     search, merge them (step 9):
      │                                     catches "IT-AUP-2026"
      ├╌╌ ✗  Time-aware ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ prefer the version valid on the
      │                                     date asked; needs several versions
      │                                     of a policy
      ├╌╌ ✗  Graph RAG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ walk the entity graph to collect
      │                                     linked chunks; for questions about
      │                                     relationships
      ▼
   candidate chunks
```

**Tried**
- v1, the right chunk was in the top 3, 5 and 10 for 92.5%, 95.5% and
  97.7% → a ranking problem → reranking
- v2, hybrid (hand-written BM25 + RRF): 97.34% → 96.97%, 0 fixed,
  1 broken; 4 of the 7 misses are in the dense top 10 but dropped by
  the reranker

[↑ Overview](#overview)

## 9. Fuse

Merge two or more result lists.

```text
   two or more lists
      │
      ▼
   9 FUSE
      │
      ├╌╌ ⬜ Weighted fusion / DBSF ╌╌ combine the raw scores, with one list
      │                                weighted higher
      ├╌╌ ⬜ Deduplication ╌╌╌╌╌╌╌╌╌╌╌ keep one copy when the same chunk comes
      │                                from several searches
      ├╌╌ ✗  RRF ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ score each chunk by its rank in every
      │                                list, 1 / (60 + rank), and add up; the
      │                                lists' score scales don't matter
      ▼
   one list
```

**Tried**: v2, RRF (k = 60) merged dense and BM25 for hybrid search;
no gain, see step 8

[↑ Overview](#overview)

## 10. Rerank

Fetch more, score again with question + chunk together, keep the best.

```text
   10 candidates
      │
      ▼
   10 RERANK
      │
      ├╌╌ ✅ BGE reranker v2-m3 ╌╌╌╌╌╌╌╌╌╌ a model reads question and chunk
      │                                    together and scores them; 10
      │                                    candidates → best 3
      ├╌╌ ⬜ FlashRank ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a smaller, faster reranker, for when
      │                                    ours is too slow
      ├╌╌ ⬜ LLM reranker ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ ask an LLM to score each candidate;
      │                                    slowest, one call per chunk
      ├╌╌ ✗  Cohere ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a hosted reranker API; paid, and we
      │                                    run local
      ├╌╌ ✗  ColBERT / learning-to-rank ╌╌ word-by-word scoring / a model
      │                                    trained on click or label data; for
      │                                    big collections with many labels
      ▼
   top 3
```

**Tried**: v2, 10 → 3: none 92.4% · base 95.4% (0.24s) · v2-m3 96.6%
(0.85s); v2-m3 in use since 5 Nov

**Watch out**: when every score is near 0, the order is noise

[↑ Overview](#overview)

## 11. Refine

Decide what reaches the prompt.

```text
   ranked chunks
      │
      ▼
   11 REFINE
      │
      ├╌╌ ✅ Top-K = 3 ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ pass the K best chunks; K = 5 gave no
      │                                  better answers (basic-rag)
      ├╌╌ ⬜ Diversity / dedup ╌╌╌╌╌╌╌╌╌ skip chunks that repeat what's already
      │                                  picked: a fact repeated in two
      │                                  chapters
      ├╌╌ ⬜ Parent expansion ╌╌╌╌╌╌╌╌╌╌ swap a chunk that's too small to
      │                                  answer from for its whole section
      ├╌╌ ⬜ Compression ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ keep only the sentences that matter in
      │                                  each chunk
      ├╌╌ ✗  Reranker score threshold ╌╌ drop chunks below a reranker score; if
      │                                  none are left, say "I can't tell"
      ├╌╌ ✗  Similarity threshold ╌╌╌╌╌╌ drop chunks below a vector score; no
      │                                  clean cut-off (v1)
      ├╌╌ ✗  MMR ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ pick chunks that are relevant but
      │                                  different from each other; pushed out
      │                                  good chunks (v1)
      ▼
   chunks for the prompt
```

**Tried**: v2, reranker score threshold: casual questions the handbooks
cover scored lower (0.004) than ones they don't (0.22); no clean
cut-off

[↑ Overview](#overview)

## 12. Generate

Prompt the model with the chunks and the question.

```text
   chunks + question
      │
      ▼
   12 GENERATE
      │
      ├╌╌ ✅ Grounding rules ╌╌╌╌╌╌╌╌ tell the model to answer only from the
      │                               chunks, else "I can't tell"
      ├╌╌ ✅ Labelled context ╌╌╌╌╌╌╌ put each chunk's source above it, so
      │                               India's rule isn't mixed with the US one
      ├╌╌ ✅ Self-check ╌╌╌╌╌╌╌╌╌╌╌╌╌ the model re-reads its answer against the
      │                               chunks before replying (rule 9)
      ├╌╌ ✅ Prompt refresh ╌╌╌╌╌╌╌╌╌ rewrite the rules for all 6 handbooks:
      │                               one rule per mistake type
      ├╌╌ ⏭ Claim-level citations ╌╌ tag each claim with its section: "free in
      │                               the garage [Facilities 6.4]"
      ├╌╌ ⬜ Structured output ╌╌╌╌╌╌ make the model return JSON of a fixed
      │                               shape, for code to read
      ├╌╌ ⬜ Streaming ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ show the answer word by word as it's
      │                               written
      ├╌╌ ✗  Lost in the middle ╌╌╌╌╌ put the best chunks first and last;
      │                               matters with many chunks, we send 3
      ▼
   answer
```

**Tried**
- v2, 9 wrong answers had the right chunk (payroll vs office, invented
  visitor rules) → citations + faithfulness check
- v2, prompt refresh: a draw (94.6% vs 95.1%, gemma3:4b judge), but
  "Policy topic:" leaks 40 → 0; forcing "begin with Yes/No" backfired
- v2, Gemma 4 judge: 76 of 90 imperfect answers had the right chunk;
  most say the wrong yes/no (14) or make up an answer instead of "I
  can't tell" (6) → the small answer model is now the biggest lever

[↑ Overview](#overview)

## 13. Verify

Check the answer before returning it; loop back if it's weak.

```text
   answer
      │
      ▼
   13 VERIFY
      │
      ├╌╌ ⬜ Citation check ╌╌╌╌╌╌╌╌╌ confirm each cited section really says
      │                               it, for that office: 6.4 is Austin, not
      │                               Pune
      ├╌╌ ⬜ Faithfulness ╌╌╌╌╌╌╌╌╌╌╌ check each claim against the chunks; drop
      │                               unsupported ones, like invented visitor
      │                               rules
      ├╌╌ ⬜ CRAG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ grade the chunks; if poor, rewrite and
      │                               search again, or say "I can't tell"
      │                               (LangGraph)
      ├╌╌ ⬜ Iterative / recursive ╌╌ search, read, search again until the
      │                               answer is complete
      ├╌╌ ⬜ Self-RAG / agentic ╌╌╌╌╌ the model itself decides when to search
      │                               and with which tool
      ▼
   checked answer
```

[↑ Overview](#overview)

## 14. Measure

Score the chunks first, then the answer.

```text
   top chunks · answer
      │
      ▼
   14 MEASURE
      │
      ├╌╌ ✅ Hit Rate · Recall · MRR ╌╌ did an expected section come back, how
      │                                 many, how high: 259 of 266 → 97.4%
      ├╌╌ ✅ LLM judge ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ a second LLM scores each answer 0–2 on
      │                                 correctness, context support and
      │                                 completeness: Gemma 4 26B (Google,
      │                                 free)
      ├╌╌ ✅ Judge vs human ╌╌╌╌╌╌╌╌╌╌╌ hand-score answers to check the judge
      │                                 before trusting a 1–2% change: a
      │                                 40-answer key
      ├╌╌ ✅ Dev / test split ╌╌╌╌╌╌╌╌╌ tune on one set of questions, report on
      │                                 the other: dev 171 · test 114
      ├╌╌ ⏭ Regression gate ╌╌╌╌╌╌╌╌╌╌ block a change that drops below the
      │                                 baseline: Hit Rate ≥ 97.4%
      ├╌╌ 🧪 Latency ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ time per question, per step: the
      │                                 reranker adds 0.85s
      ├╌╌ ⬜ Precision@K ╌╌╌╌╌╌╌╌╌╌╌╌╌╌ share of returned chunks that are
      │                                 useful: 1 of 3 → 0.33
      ├╌╌ ⬜ Tracing ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ record every step of one question to
      │                                 see why it failed (LangSmith)
      ├╌╌ ✗  MAP / NDCG ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ ranking scores that need graded labels;
      │                                 ours are yes/no
      ▼
   scores
```

**Rules**: a 1–2% swing is judge noise. Fix the labels before the
pipeline (also_correct: 87.8% → 92.4% with no code change). Only
compare scores from the same judge: on the same answers gemma3:4b gave
94.4%, Gemma 4 26B 87.9%

**Tried**: v2, judges vs the 40-answer key: gemma3:4b 20/40 ·
gemma3:12b 29/40 · Gemma 4 26B 28/35 · Nemotron 3 Ultra 35/40; Gemma 4
picked (free, and a full run fits one sitting)

[↑ Overview](#overview)

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
summaries (4), keyword enrichment and glossary rules (3), generation
(12), verification (13), judge, tracing and gates (14).
