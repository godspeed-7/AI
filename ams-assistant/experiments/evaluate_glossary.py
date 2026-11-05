"""Experiment: do glossary rules (ams-data/glossary.csv) improve
retrieval, on the chunk side or on the question side?

In:  the handbooks (chunked exactly as ingest.py does), the glossary,
     and the answerable questions in ams-data/evaluation_questions.csv.
Out: --preview: every chunk and question a rule fires on, with what it
     adds. Otherwise Hit Rate, Recall and MRR @TOP_K, each against the
     same baseline:
         Chunk side      search GLOSSARY_COLLECTION_NAME: the chunks
                         with their "Glossary: ..." line
         Question side   search COLLECTION_NAME with the expanded
                         question, e.g. "... (United States, US payroll)"
     plus every question that flipped.

Strategy: no LLM. Same scoring (ams_assistant/evaluation.py) for every
run. With USE_RERANKER (config.py), every run fetches CANDIDATE_K and
the cross-encoder keeps TOP_K, reranking with its own question text.

Usage (from ams-assistant/):
    uv run python experiments/evaluate_glossary.py --preview
    uv run python experiments/evaluate_glossary.py

Caveats:
- The chunk side re-embeds every chunk into its own collection (about
  a minute); COLLECTION_NAME is never touched.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import argparse
import sys
from pathlib import Path

from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import (
    CANDIDATE_K,
    GLOSSARY_COLLECTION_NAME,
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
from ams_assistant.glossary import enrich_chunk, expand_question
from ams_assistant.vector_store import get_embeddings, get_vector_store

# ingest.py sits in the project root, one folder up from this script,
# and isn't part of the ams_assistant package: make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingest import load_documents, split_documents  # noqa: E402


def glossary_line(doc) -> str:
    """The chunk's "Glossary: ..." line, or "" if it has none."""
    last = doc.page_content.rsplit("\n", 1)[-1]
    return last if last.startswith("Glossary: ") else ""


def preview(chunks, questions) -> None:
    """Print where the rules fire, so misfires can get a skip."""
    print("Chunk side")
    enriched = 0
    for chunk in chunks:
        line = glossary_line(enrich_chunk(chunk))
        if line:
            enriched += 1
            print(f"  {chunk.metadata['source']}#"
                  f"{chunk.metadata['section']} "
                  f"{chunk.metadata['section_title']}: {line}")
    print(f"  -> {enriched} of {len(chunks)} chunks get a line")

    print("\nQuestion side")
    expanded = [q["question"] for q in questions
                if expand_question(q["question"]) != q["question"]]
    for text in expanded:
        print(f"  {expand_question(text)}")
    print(f"  -> {len(expanded)} of {len(questions)} questions expanded")


def main():
    """Preview the rules, or score both sides against the baseline."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true",
                        help="only show where the rules fire")
    args = parser.parse_args()

    chunks = split_documents(load_documents())
    questions = [q for q in load_questions() if q["expected_source"].strip()]

    if args.preview:
        preview(chunks, questions)
        return

    print(f"Embedding {len(chunks)} chunks into "
          f"'{GLOSSARY_COLLECTION_NAME}'...")
    glossary_store = QdrantVectorStore.from_documents(
        [enrich_chunk(chunk) for chunk in chunks],
        get_embeddings(),
        url=QDRANT_URL,
        collection_name=GLOSSARY_COLLECTION_NAME,
        force_recreate=True,
    )

    texts = [q["question"] for q in questions]
    expanded = [expand_question(text) for text in texts]
    k = CANDIDATE_K if USE_RERANKER else TOP_K
    retriever = get_vector_store().as_retriever(search_kwargs={"k": k})

    runs = {
        "baseline": (texts, retriever.batch(texts)),
        "chunk": (texts, glossary_store.as_retriever(
            search_kwargs={"k": k}).batch(texts)),
        "question": (expanded, retriever.batch(expanded)),
    }

    if USE_RERANKER:
        # Imported here: loading PyTorch takes seconds, and it isn't
        # needed when USE_RERANKER is off.
        from ams_assistant.reranker import rerank

        print(f"Reranking {CANDIDATE_K} -> {TOP_K} for every run...")
        runs = {
            name: (run_texts, [rerank(t, d)
                               for t, d in zip(run_texts, docs)])
            for name, (run_texts, docs) in runs.items()
        }

    scores = {name: [] for name in runs}
    for i, item in enumerate(questions):
        expected = expected_groups(item)
        for name, (_texts, docs) in runs.items():
            scores[name].append(score(expected, docs[i]))

    chunk_details = [
        f"top = {d[0].metadata['source']}#{d[0].metadata['section']} "
        f"{glossary_line(d[0])}"
        for d in runs["chunk"][1]
    ]
    print("\n=== Chunk side ===")
    print_comparison("Chunk", questions, scores["baseline"],
                     scores["chunk"], chunk_details)
    print("\n=== Question side ===")
    print_comparison("Question", questions, scores["baseline"],
                     scores["question"], expanded)


if __name__ == "__main__":
    main()
