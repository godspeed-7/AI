"""Retrieval evaluation: does the retriever find the right policy
section?

In:  ams-data/evaluation_questions.csv; each answerable question lists
     its expected sections as "document#section" (e.g.
     "leave_policy_india.txt#4.1").
Out: Hit Rate, Recall and MRR (all "@TOP_K"), computed exactly as in
     basic-rag/evals/evaluate_retrieval.py, plus the questions that
     missed. No LLM is involved, so it takes seconds.

Strategy: our chunks carry only "source", not a section number. So a
chunk's sections are read from its text: every heading line in it
("4. ANNUAL LEAVE CARRY-OVER", "4.1 Standard carry-over limit") gives
one, e.g. {"leave_policy_india.txt#4", "leave_policy_india.txt#4.1"}.

Caveats:
- A chunk that continues a section without repeating its heading has
  no section, so it never counts as a hit, even when it holds the
  answer. A chunk that only has a heading at its end still counts.
  The scores are therefore close to, not equal to, basic-rag's.
- Unanswerable questions (no expected section) are skipped.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

import csv
import re

from langchain_core.documents import Document

from ams_assistant.config import EVALUATION_FILE, TOP_K
from ams_assistant.vector_store import get_vector_store


# Same heading rule as basic-rag's chunker: a line starting with a
# number like "4." or "4.1" followed by a title.
HEADING_PATTERN = re.compile(r"(?m)^[ \t]*(\d+(?:\.\d+)*)\.?[ \t]+\S")


def load_questions() -> list[dict]:
    """Read the CSV; each row is a dict with keys question,
    expected_answer, expected_source, category, and split."""
    with open(EVALUATION_FILE, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def expected_keys(expected_source: str) -> set[str]:
    """Turn "a.txt#4.1; b.txt#2" into {"a.txt#4.1", "b.txt#2"}."""
    return {key.strip() for key in expected_source.split(";") if key.strip()}


def chunk_keys(doc: Document) -> set[str]:
    """Return the "document#section" keys of every heading in a chunk,
    or an empty set if it has none."""
    source = doc.metadata["source"]
    return {
        f"{source}#{number}"
        for number in HEADING_PATTERN.findall(doc.page_content)
    }


def main():
    """Score the retriever on every question and print the metrics."""
    # Only questions with an expected source can be scored.
    questions = [q for q in load_questions() if q["expected_source"].strip()]
    retriever = get_vector_store().as_retriever(search_kwargs={"k": TOP_K})

    print(f"Scoring {len(questions)} questions, top {TOP_K} chunks each...")

    # Running totals; divided by the question count at the end.
    hits = 0
    recall_sum = 0.0
    mrr_sum = 0.0
    failures = []

    for item in questions:
        expected = expected_keys(item["expected_source"])
        docs = retriever.invoke(item["question"])

        # One set of keys per chunk, in rank order (needed for MRR).
        keys_per_chunk = [chunk_keys(doc) for doc in docs]
        retrieved = set().union(*keys_per_chunk)
        matched = expected & retrieved

        # Hit Rate: at least one expected section was retrieved.
        if matched:
            hits += 1
        else:
            failures.append((item, docs, keys_per_chunk))

        # Recall: share of the expected sections retrieved.
        recall_sum += len(matched) / len(expected)

        # MRR: 1 / rank of the first chunk with an expected section.
        for rank, keys in enumerate(keys_per_chunk, start=1):
            if keys & expected:
                mrr_sum += 1 / rank
                break

    total = len(questions)
    print(f"\nHit Rate@{TOP_K} : {hits / total * 100:.2f}% ({hits}/{total})")
    print(f"Recall@{TOP_K}   : {recall_sum / total:.4f}")
    print(f"MRR@{TOP_K}      : {mrr_sum / total:.4f}")

    print(f"\nMissed questions ({len(failures)}):")

    for index, (item, docs, keys_per_chunk) in enumerate(failures, start=1):
        print(f"\n{index}. {item['question']}")
        print(f"   Expected : {item['expected_source']}")

        for rank, (doc, keys) in enumerate(zip(docs, keys_per_chunk), 1):
            # "(no heading)" = a continuation chunk; see Caveats.
            found = ", ".join(sorted(keys)) or "(no heading)"
            print(f"   [{rank}] {doc.metadata['source']}: {found}")


if __name__ == "__main__":
    main()
