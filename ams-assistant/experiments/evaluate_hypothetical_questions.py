"""Experiment: do hypothetical questions (LLM-written questions per
chunk, each stored as an extra point) improve retrieval?

In:  the handbooks (chunked exactly as ingest.py does) and the
     answerable questions in ams-data/evaluation_questions.csv.
Out: experiments/questions.json (the questions per chunk), then Hit
     Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline       search COLLECTION_NAME (what ingest.py stored)
         Hypothetical   search HYPOTHETICAL_COLLECTION_NAME: every
                        chunk's own point plus one per question, each
                        question point swapped for its chunk
     plus every question that flipped, with the point that matched.

Strategy: stage 1 writes the questions (question_writer.py), saving
as it goes; a rerun skips chunks already in questions.json. Stage 2
stores the points and searches by hand: fetch FETCH_FACTOR times more
points than needed, swap each for its parent chunk, drop repeats, keep
the first k (what LangChain's MultiVectorRetriever does). With
USE_RERANKER (config.py), k = CANDIDATE_K and the cross-encoder keeps
TOP_K.

Usage (from ams-assistant/, as one line each):
    uv run python experiments/evaluate_hypothetical_questions.py
        --questions-only
    uv run python experiments/evaluate_hypothetical_questions.py

Caveats:
- Stage 1 is one LLM call per chunk (370): slow the first time, free
  after. Run nothing else heavy meanwhile.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import (
    CANDIDATE_K,
    HYPOTHETICAL_COLLECTION_NAME,
    QDRANT_URL,
    TOP_K,
    USE_RERANKER,
)
from ams_assistant.evaluation import (
    expected_groups,
    load_questions,
    print_comparison,
    score,
)
from ams_assistant.question_writer import build_question_writer
from ams_assistant.vector_store import get_embeddings, get_vector_store

# ingest.py sits in the project root, one folder up from this script,
# and isn't part of the ams_assistant package: make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import load_documents, split_documents  # noqa: E402

QUESTIONS_FILE = Path(__file__).with_name("questions.json")
# Several points can lead to the same chunk, so fetch this many times
# more points than the chunks we need.
FETCH_FACTOR = 4


def chunk_key(chunk: Document) -> str:
    """"employee_handbook.txt#13.5": the chunk's first section."""
    return f"{chunk.metadata['source']}#{chunk.metadata['section']}"


def write_questions(chunks: list[Document]) -> dict[str, list[str]]:
    """Stage 1: the questions per chunk, saved after every batch."""
    saved = {}
    if QUESTIONS_FILE.exists():
        saved = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))

    todo = [c for c in chunks if chunk_key(c) not in saved]
    print(f"Questions: {len(saved)} chunks saved, {len(todo)} to write")
    writer = build_question_writer()
    start = time.perf_counter()

    # 10 chunks per batch, 2 at a time (OLLAMA_NUM_PARALLEL=2); saving
    # after each batch means a stopped run loses at most 10.
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        results = writer.batch(
            [{"chunk": c.page_content} for c in batch],
            config={"max_concurrency": 2},
        )
        for chunk, questions in zip(batch, results):
            saved[chunk_key(chunk)] = questions
        QUESTIONS_FILE.write_text(
            json.dumps(saved, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        minutes = (time.perf_counter() - start) / 60
        last = chunk_key(batch[-1])
        print(f"[{i + len(batch)}/{len(todo)}, {minutes:.1f} min] "
              f"{last}: {saved[last]}", flush=True)

    return saved


def store_points(chunks: list[Document],
                 questions: dict[str, list[str]]) -> QdrantVectorStore:
    """Stage 2: one point per chunk and one per question, each with
    "parent" = its chunk's key (collection recreated every run)."""
    points = []
    for chunk in chunks:
        key = chunk_key(chunk)
        points.append(Document(
            page_content=chunk.page_content,
            metadata={"parent": key, "kind": "chunk"},
        ))
        points += [
            Document(page_content=q,
                     metadata={"parent": key, "kind": "question"})
            for q in questions[key]
        ]

    print(f"Embedding {len(points)} points into "
          f"'{HYPOTHETICAL_COLLECTION_NAME}'...")
    return QdrantVectorStore.from_documents(
        points,
        get_embeddings(),
        url=QDRANT_URL,
        collection_name=HYPOTHETICAL_COLLECTION_NAME,
        force_recreate=True,
    )


def to_parents(points: list[Document], parents: dict[str, Document],
               k: int) -> tuple[list[Document], list[Document]]:
    """Swap each point for its chunk, drop repeats, keep the first k.
    Also return the point that brought in each kept chunk."""
    chunks, via = [], []
    for point in points:
        chunk = parents[point.metadata["parent"]]
        if chunk not in chunks:
            chunks.append(chunk)
            via.append(point)
        if len(chunks) == k:
            break
    return chunks, via


def main():
    """Write the questions, then score both runs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions-only", action="store_true",
                        help="stop after writing the questions")
    args = parser.parse_args()

    chunks = split_documents(load_documents())
    parents = {chunk_key(c): c for c in chunks}
    assert len(parents) == len(chunks), "two chunks share a key"

    questions = write_questions(chunks)
    if args.questions_only:
        return

    store = store_points(chunks, questions)

    items = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in items]
    k = CANDIDATE_K if USE_RERANKER else TOP_K
    baseline_docs = get_vector_store().as_retriever(
        search_kwargs={"k": k}).batch(texts)
    found = store.as_retriever(
        search_kwargs={"k": k * FETCH_FACTOR}).batch(texts)
    swapped = [to_parents(points, parents, k) for points in found]
    hypothetical_docs = [docs for docs, _via in swapped]

    if USE_RERANKER:
        # Imported here: loading PyTorch takes seconds, and it isn't
        # needed when USE_RERANKER is off.
        from ams_assistant.reranker import rerank

        print(f"Reranking {CANDIDATE_K} -> {TOP_K} for both runs...")
        baseline_docs = [rerank(t, d) for t, d in zip(texts, baseline_docs)]
        hypothetical_docs = [
            rerank(t, d) for t, d in zip(texts, hypothetical_docs)
        ]

    baseline = []
    hypothetical = []
    for item, docs_a, docs_b in zip(items, baseline_docs,
                                    hypothetical_docs):
        expected = expected_groups(item)
        baseline.append(score(expected, docs_a))
        hypothetical.append(score(expected, docs_b))

    # For a flipped question: which point brought in the new top chunk.
    details = []
    for docs, (kept, via) in zip(hypothetical_docs, swapped):
        top = docs[0]
        point = via[kept.index(top)]
        how = (f"question \"{point.page_content}\""
               if point.metadata["kind"] == "question" else "its own text")
        details.append(f"top = {chunk_key(top)}, matched via {how}")
    print_comparison("Hypothet.", items, baseline, hypothetical, details)


if __name__ == "__main__":
    main()
