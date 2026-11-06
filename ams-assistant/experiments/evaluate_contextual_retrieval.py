"""Experiment: does contextual retrieval (an LLM-written context line
on top of every chunk) improve retrieval?

In:  the chunks exactly as ingest.py stores them (build_chunks) and the
     answerable questions in ams-data/evaluation_questions.csv.
Out: experiments/contexts.json (one context line per chunk), then
     Hit Rate, Recall and MRR @TOP_K for two pipelines, side by side:
         Baseline     PRODUCTION (pipeline.py)
         Contextual   PRODUCTION searching CONTEXTUAL_COLLECTION_NAME:
                      the same chunks with "Context: <line>" on top
     plus every question that flipped, with the context line of the
     new top chunk.

Strategy: stage 1 writes the context lines (contextualizer.py),
handbook by handbook, saving after every chunk; a rerun skips lines
already in contexts.json. Stage 2 embeds the contextual chunks into
their own collection; compare() (evaluation.py) scores both pipelines.

Usage (from ams-assistant/):
    uv run python experiments/evaluate_contextual_retrieval.py --contexts-only
    uv run python experiments/evaluate_contextual_retrieval.py

Caveats:
- Stage 1 is one LLM call per chunk (370), each with a whole handbook:
  slow the first time, free after. Run nothing else heavy meanwhile.
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

from ams_assistant.config import (
    CONTEXT_NUM_CTX,
    CONTEXTUAL_COLLECTION_NAME,
    QDRANT_URL,
)
from ams_assistant.contextualizer import build_contextualizer, one_line
from ams_assistant.evaluation import compare
from ams_assistant.pipeline import PRODUCTION
from ams_assistant.vector_store import get_embeddings

# ingest.py sits in the project root, one folder up from this script,
# and isn't part of the ams_assistant package: make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import build_chunks, load_documents  # noqa: E402

CONTEXTS_FILE = Path(__file__).with_name("contexts.json")


def chunk_key(chunk: Document) -> str:
    """"employee_handbook.txt#3.4": the chunk's first section."""
    return f"{chunk.metadata['source']}#{chunk.metadata['section']}"


def write_contexts(documents: list[Document],
                   chunks: list[Document]) -> dict[str, str]:
    """Stage 1: one context line per chunk, saved after each call."""
    contexts = {}
    if CONTEXTS_FILE.exists():
        contexts = json.loads(CONTEXTS_FILE.read_text(encoding="utf-8"))

    todo = [c for c in chunks if chunk_key(c) not in contexts]
    print(f"Context lines: {len(contexts)} saved, {len(todo)} to write")
    if not todo:
        return contexts

    handbooks = {doc.metadata["source"]: doc.page_content
                 for doc in documents}
    contextualizer = build_contextualizer()
    start = time.perf_counter()

    # chunks are already in handbook order, so calls for one handbook
    # come one after another and Ollama can reuse its prompt.
    for done, chunk in enumerate(todo, start=1):
        message = contextualizer.invoke({
            "document": handbooks[chunk.metadata["source"]],
            "chunk": chunk.page_content,
        })
        tokens = message.usage_metadata["input_tokens"]
        if tokens >= CONTEXT_NUM_CTX - 50:
            print(f"  WARNING: {tokens} prompt tokens; the handbook was "
                  f"probably cut. Raise CONTEXT_NUM_CTX.")

        key = chunk_key(chunk)
        contexts[key] = one_line(message.content)
        CONTEXTS_FILE.write_text(
            json.dumps(contexts, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        minutes = (time.perf_counter() - start) / 60
        print(f"[{done}/{len(todo)}, {minutes:.1f} min, {tokens} tokens] "
              f"{key}: {contexts[key]}", flush=True)

    return contexts


def store_contextual(chunks: list[Document],
                     contexts: dict[str, str]) -> QdrantVectorStore:
    """Stage 2: embed "Context: <line>" + chunk into its own
    collection (recreated every run)."""
    docs = [
        Document(
            page_content=f"Context: {contexts[chunk_key(c)]}\n"
                         + c.page_content,
            metadata=c.metadata,
        )
        for c in chunks
    ]
    print(f"Embedding {len(docs)} chunks into "
          f"'{CONTEXTUAL_COLLECTION_NAME}'...")
    return QdrantVectorStore.from_documents(
        docs,
        get_embeddings(),
        url=QDRANT_URL,
        collection_name=CONTEXTUAL_COLLECTION_NAME,
        force_recreate=True,
    )


def main():
    """Write the context lines, then score both pipelines."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--contexts-only", action="store_true",
                        help="stop after writing the context lines")
    args = parser.parse_args()

    documents = load_documents()
    chunks = build_chunks(documents)
    keys = [chunk_key(c) for c in chunks]
    assert len(set(keys)) == len(keys), "two chunks share a key"

    contexts = write_contexts(documents, chunks)
    if args.contexts_only:
        return

    store_contextual(chunks, contexts)
    compare(PRODUCTION, {
        "Contextual": replace(PRODUCTION,
                              collection=CONTEXTUAL_COLLECTION_NAME),
    })


if __name__ == "__main__":
    main()
