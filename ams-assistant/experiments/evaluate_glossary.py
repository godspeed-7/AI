"""Experiment: do glossary rules (ams-data/glossary.csv) improve
retrieval, on the chunk side or on the question side?

In:  the handbooks (chunked exactly as ingest.py does), the glossary,
     and the answerable questions in ams-data/evaluation_questions.csv.
Out: --preview: every chunk and question a rule fires on, with what it
     adds. Otherwise Hit Rate, Recall and MRR @TOP_K, each against the
     same baseline (PRODUCTION, pipeline.py):
         Chunk       PRODUCTION searching GLOSSARY_COLLECTION_NAME: the
                     chunks with their "Glossary: ..." line
         Question    PRODUCTION with question_glossary on: the
                     question gets "(United States, US payroll)" etc.
         Both        the two together
     plus every question that flipped.

Strategy: no LLM. compare() (evaluation.py) runs every pipeline with
the same steps and scoring; only the glossary field differs.

Usage (from ams-assistant/):
    uv run python experiments/evaluate_glossary.py --preview
    uv run python experiments/evaluate_glossary.py

Caveats:
- The chunk side was promoted on 2026-11-05 (ingest.py adds the lines
  to COLLECTION_NAME), so Chunk now matches the baseline and Question
  tests both sides together (3 fixed, 1 broken when it was tried).
- The chunk side re-embeds every chunk into its own collection (about
  a minute); COLLECTION_NAME is never touched.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import GLOSSARY_COLLECTION_NAME, QDRANT_URL
from ams_assistant.evaluation import compare, load_questions
from ams_assistant.glossary import enrich_chunk, expand_question
from ams_assistant.pipeline import PRODUCTION
from ams_assistant.vector_store import get_embeddings

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

    if args.preview:
        questions = [q for q in load_questions()
                     if q["expected_source"].strip()]
        preview(chunks, questions)
        return

    print(f"Embedding {len(chunks)} chunks into "
          f"'{GLOSSARY_COLLECTION_NAME}'...")
    QdrantVectorStore.from_documents(
        [enrich_chunk(chunk) for chunk in chunks],
        get_embeddings(),
        url=QDRANT_URL,
        collection_name=GLOSSARY_COLLECTION_NAME,
        force_recreate=True,
    )

    compare(PRODUCTION, {
        "Chunk": replace(PRODUCTION, collection=GLOSSARY_COLLECTION_NAME),
        "Question": replace(PRODUCTION, question_glossary=True),
        "Both": replace(PRODUCTION, collection=GLOSSARY_COLLECTION_NAME,
                        question_glossary=True),
    })


if __name__ == "__main__":
    main()
