"""Experiment: does contextual retrieval (an LLM-written context line
on top of every chunk) improve retrieval?

In:  the handbooks (chunked exactly as ingest.py does) and the
     answerable questions in ams-data/evaluation_questions.csv.
Out: experiments/contexts.json (one context line per chunk), then
     Hit Rate, Recall and MRR @TOP_K for two runs, side by side:
         Baseline     search COLLECTION_NAME (what ingest.py stored)
         Contextual   search CONTEXTUAL_COLLECTION_NAME: the same
                      chunks with "Context: <line>" on top
     plus every question that flipped, with the context line of the
     new top chunk.

Strategy: stage 1 writes the context lines (contextualizer.py),
handbook by handbook, saving after every chunk; a rerun skips lines
already in contexts.json. Stage 2 embeds the contextual chunks into
their own collection and scores both runs with the same functions.
With USE_RERANKER (config.py), both runs fetch CANDIDATE_K and the
cross-encoder keeps TOP_K.

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
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import (
    CANDIDATE_K,
    CONTEXT_NUM_CTX,
    CONTEXTUAL_COLLECTION_NAME,
    QDRANT_URL,
    TOP_K,
    USE_RERANKER,
)
from ams_assistant.contextualizer import build_contextualizer, one_line
from ams_assistant.evaluation import (
    expected_groups,
    load_questions,
    print_comparison,
    score,
)
from ams_assistant.vector_store import get_embeddings, get_vector_store

# ingest.py sits in the project root, one folder up from this script,
# and isn't part of the ams_assistant package: make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import load_documents, split_documents  # noqa: E402

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
    """Write the context lines, then score both runs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--contexts-only", action="store_true",
                        help="stop after writing the context lines")
    args = parser.parse_args()

    documents = load_documents()
    chunks = split_documents(documents)
    keys = [chunk_key(c) for c in chunks]
    assert len(set(keys)) == len(keys), "two chunks share a key"

    contexts = write_contexts(documents, chunks)
    if args.contexts_only:
        return

    contextual_store = store_contextual(chunks, contexts)

    questions = [q for q in load_questions() if q["expected_source"].strip()]
    texts = [q["question"] for q in questions]
    k = CANDIDATE_K if USE_RERANKER else TOP_K
    baseline_docs = get_vector_store().as_retriever(
        search_kwargs={"k": k}).batch(texts)
    contextual_docs = contextual_store.as_retriever(
        search_kwargs={"k": k}).batch(texts)

    if USE_RERANKER:
        # Imported here: loading PyTorch takes seconds, and it isn't
        # needed when USE_RERANKER is off.
        from ams_assistant.reranker import rerank

        print(f"Reranking {CANDIDATE_K} -> {TOP_K} for both runs...")
        baseline_docs = [rerank(t, d) for t, d in zip(texts, baseline_docs)]
        contextual_docs = [
            rerank(t, d) for t, d in zip(texts, contextual_docs)
        ]

    baseline = []
    contextual = []
    for item, docs_a, docs_b in zip(questions, baseline_docs,
                                    contextual_docs):
        expected = expected_groups(item)
        baseline.append(score(expected, docs_a))
        contextual.append(score(expected, docs_b))

    # For a flipped question, show the new top chunk's context line.
    details = [
        f"top = {chunk_key(docs[0])}: {contexts[chunk_key(docs[0])]}"
        for docs in contextual_docs
    ]
    print_comparison("Contextual", questions, baseline, contextual, details)


if __name__ == "__main__":
    main()
