"""The retrieval pipeline as settings: a Pipeline says which technique
each step uses, and retrieve() runs the steps in order.

In:  questions (strings) and a Pipeline (default PRODUCTION).
Out: retrieve(questions, pipeline) -> per question, the top_k
     Documents, best first.

Strategy: the app (chain.py) and every experiment call the same
retrieve(), so an experiment is PRODUCTION with one field changed and
nothing else can differ. Steps: Transform (rewrite, decompose, then
question_glossary) -> Retrieve (vector search in `collection`, merged
with keyword search if hybrid, then swap_to_parents) -> Rerank ->
Fuse (with decompose: the parts' results merged by taking turns).
Promoting a technique = changing its default in Pipeline.

Caveats:
- Ingestion-side techniques are picked by `collection`: build that
  collection first (its experiments/ script does).
- Swap and rerank use the transformed text, not the original question.
- With decompose, a search text holds one sub-question per line
  (PART_SEPARATOR), so transform() still returns one string per
  question.
"""

from dataclasses import dataclass
from functools import cache

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import models

from ams_assistant.config import CANDIDATE_K, COLLECTION_NAME, TOP_K
from ams_assistant.decomposer import build_decomposer
from ams_assistant.glossary import expand_question
from ams_assistant.keyword_search import keyword_search
from ams_assistant.rewriter import build_rewriter
from ams_assistant.tracing import doc_lines, traced
from ams_assistant.vector_store import get_vector_store

# With swap_to_parents several points can lead to the same chunk, so
# fetch this many times more points than the chunks needed.
FETCH_FACTOR = 4
# Between the sub-questions in one search text (decompose).
PART_SEPARATOR = "\n"
# RRF's usual constant: a list's 1st place earns 1/61, its 10th 1/70,
# so being found by both searches beats ranking high in one.
RRF_K = 60


# frozen=True: a Pipeline can't be changed once made, only copied with
# changes: dataclasses.replace(PRODUCTION, rerank=False) is like JS
# {...PRODUCTION, rerank: false}.
@dataclass(frozen=True)
class Pipeline:
    """One field per technique; the defaults are what the app runs."""

    # Ingestion side: the collection to search. Experiments build
    # copies whose chunks carry glossary or context lines.
    collection: str = COLLECTION_NAME
    # Retrieve: also run keyword search (keyword_search.py) and merge
    # the two rankings with RRF before reranking.
    hybrid: bool = False
    # The collection's points are questions (or summaries) that lead to
    # a chunk via metadata["parent"]: swap each for that chunk.
    swap_to_parents: bool = False
    # Transform: an LLM rewrite (rewriter.py), an LLM split into
    # sub-questions (decomposer.py), then the glossary's additions in
    # brackets (glossary.py).
    rewrite: bool = False
    decompose: bool = False
    question_glossary: bool = False
    # Rerank: the cross-encoder keeps top_k of candidate_k (reranker.py).
    # Promoted 2026-11-05 (top 3: 92.40% -> 96.58%).
    rerank: bool = True
    candidate_k: int = CANDIDATE_K
    top_k: int = TOP_K


PRODUCTION = Pipeline()


def transform(questions: list[str], pipeline: Pipeline) -> list[str]:
    """Transform step: the text each question is searched with."""
    texts = list(questions)
    if pipeline.rewrite:
        # .batch() is .invoke() on a list, running up to 4 calls at
        # once (like Promise.all with a concurrency limit).
        texts = build_rewriter().batch(
            [{"question": text} for text in texts],
            config={"max_concurrency": 4},
        )
    if pipeline.decompose:
        splits = build_decomposer().batch(
            [{"question": text} for text in texts],
            config={"max_concurrency": 4},
        )
        # Only a real split (2+ parts) is used: a "one part" reply is
        # often the question slightly reworded, which would change its
        # search for no reason.
        texts = [PART_SEPARATOR.join(parts) if len(parts) > 1 else text
                 for parts, text in zip(splits, texts)]
    if pipeline.question_glossary:
        texts = [PART_SEPARATOR.join(expand_question(part)
                                     for part in text.split(PART_SEPARATOR))
                 for text in texts]
    return texts


# In a traced agent run, its own step in Langfuse (tracing.py).
@traced("vector search", "retriever",
        show_input=lambda store, text, k: {"search": text, "k": k},
        show_output=doc_lines)
def search(store: QdrantVectorStore, text: str, k: int) -> list[Document]:
    """Vector search that keeps each score (cosine: higher = closer) in
    doc.metadata["score"]; as_retriever() would drop it."""
    results = store.similarity_search_with_score(text, k=k)
    for doc, score in results:
        doc.metadata["score"] = score
    return [doc for doc, _score in results]


@cache
def load_parents(collection: str) -> dict[str, Document]:
    """Every chunk point (metadata kind "chunk") in the collection, by
    its "parent" key. Read from Qdrant once per collection."""
    store = get_vector_store(collection)
    only_chunks = models.Filter(must=[models.FieldCondition(
        key="metadata.kind", match=models.MatchValue(value="chunk"),
    )])
    points, _next_page = store.client.scroll(
        collection_name=collection,
        scroll_filter=only_chunks,
        limit=10_000,
        with_payload=True,
    )
    return {
        point.payload["metadata"]["parent"]: Document(
            page_content=point.payload["page_content"],
            metadata=point.payload["metadata"],
        )
        for point in points
    }


def to_parents(points: list[Document], parents: dict[str, Document],
               k: int) -> list[Document]:
    """Swap each point for its chunk, drop repeats, keep the first k.
    A chunk brought in by a question records it in
    metadata["matched_via"]."""
    chunks = {}
    for point in points:
        key = point.metadata["parent"]
        if key in chunks:
            continue
        parent = parents[key]
        metadata = {**parent.metadata, "score": point.metadata["score"]}
        if point.metadata["kind"] != "chunk":
            metadata["matched_via"] = point.page_content
        chunks[key] = Document(page_content=parent.page_content,
                               metadata=metadata)
        if len(chunks) == k:
            break
    return list(chunks.values())


def fuse_rrf(lists: list[list[Document]], k: int) -> list[Document]:
    """Fuse ranked lists with Reciprocal Rank Fusion: each Document
    earns 1 / (RRF_K + rank) from every list it is in; keep the k
    highest totals."""
    totals = {}
    docs = {}
    for ranked in lists:
        for rank, doc in enumerate(ranked, start=1):
            key = doc.page_content
            totals[key] = totals.get(key, 0) + 1 / (RRF_K + rank)
            docs.setdefault(key, doc)
    best = sorted(totals, key=totals.get, reverse=True)[:k]
    return [docs[key] for key in best]


def take_turns(lists: list[list[Document]], k: int) -> list[Document]:
    """Fuse ranked lists by taking turns: each list's 1st, then each
    list's 2nd, ..., skipping repeats, until k. Every list gets its best
    Document in before any list gets its second."""
    merged = {}
    for rank in range(max(map(len, lists), default=0)):
        for docs in lists:
            if rank < len(docs):
                merged.setdefault(docs[rank].page_content, docs[rank])
    return list(merged.values())[:k]


def search_and_rerank(texts: list[str],
                      pipeline: Pipeline) -> list[list[Document]]:
    """Retrieve, Rerank and Fuse steps for already-transformed texts."""
    store = get_vector_store(pipeline.collection)
    k = pipeline.candidate_k if pipeline.rerank else pipeline.top_k
    parents = (load_parents(pipeline.collection)
               if pipeline.swap_to_parents else None)

    if pipeline.rerank:
        # Imported here, not at the top: it loads PyTorch, which takes
        # seconds and isn't needed when the reranker is off.
        from ams_assistant.reranker import rerank

    def find(text: str, n: int) -> list[Document]:
        found = search(store, text, n)
        if pipeline.hybrid:
            keywords = keyword_search(pipeline.collection, text, n)
            found = fuse_rrf([found, keywords], n)
        return found

    def search_one(text: str) -> list[Document]:
        if parents is not None:
            docs = to_parents(find(text, k * FETCH_FACTOR), parents, k)
        else:
            docs = find(text, k)
        if pipeline.rerank:
            return rerank(text, docs, pipeline.top_k)
        return docs

    if not pipeline.decompose:
        return [search_one(text) for text in texts]
    return [take_turns([search_one(part)
                        for part in text.split(PART_SEPARATOR)],
                       pipeline.top_k)
            for text in texts]


def retrieve(questions: list[str],
             pipeline: Pipeline = PRODUCTION) -> list[list[Document]]:
    """Run every step: per question, the top_k Documents, best first."""
    return search_and_rerank(transform(questions, pipeline), pipeline)
