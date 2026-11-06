"""Experiment: do hypothetical questions (LLM-written questions per
chunk, each stored as an extra point) improve retrieval?

In:  the chunks exactly as ingest.py stores them (build_chunks) and the
     answerable questions in ams-data/evaluation_questions.csv.
Out: experiments/questions.json (the questions per chunk), then Hit
     Rate, Recall and MRR @TOP_K for two pipelines, side by side:
         Baseline       PRODUCTION (pipeline.py)
         Hypothetical   PRODUCTION searching HYPOTHETICAL_COLLECTION_NAME
                        (every chunk's own point plus one per question)
                        with swap_to_parents on
     plus every question that flipped, with the point that matched.

Strategy: stage 1 writes the questions (question_writer.py), saving
as it goes; a rerun skips chunks already in questions.json. Stage 2
stores the points; each carries "parent" = its chunk's key, and chunk
points keep the chunk's metadata. pipeline.py's swap_to_parents does
the search: fetch more points, swap each for its chunk, drop repeats
(what LangChain's MultiVectorRetriever does).

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
from dataclasses import replace
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import HYPOTHETICAL_COLLECTION_NAME, QDRANT_URL
from ams_assistant.evaluation import compare
from ams_assistant.pipeline import PRODUCTION
from ams_assistant.question_writer import build_question_writer
from ams_assistant.vector_store import get_embeddings

# ingest.py sits in the project root, one folder up from this script,
# and isn't part of the ams_assistant package: make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import build_chunks, load_documents  # noqa: E402

QUESTIONS_FILE = Path(__file__).with_name("questions.json")


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
    """Stage 2: one point per chunk (with the chunk's metadata) and one
    per question, each with "parent" = its chunk's key (collection
    recreated every run)."""
    points = []
    for chunk in chunks:
        key = chunk_key(chunk)
        points.append(Document(
            page_content=chunk.page_content,
            metadata={**chunk.metadata, "parent": key, "kind": "chunk"},
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


def main():
    """Write the questions, then score both pipelines."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions-only", action="store_true",
                        help="stop after writing the questions")
    args = parser.parse_args()

    chunks = build_chunks(load_documents())
    keys = [chunk_key(c) for c in chunks]
    assert len(set(keys)) == len(keys), "two chunks share a key"

    questions = write_questions(chunks)
    if args.questions_only:
        return

    store_points(chunks, questions)
    compare(PRODUCTION, {
        "Hypothet.": replace(PRODUCTION,
                             collection=HYPOTHETICAL_COLLECTION_NAME,
                             swap_to_parents=True),
    })


if __name__ == "__main__":
    main()
