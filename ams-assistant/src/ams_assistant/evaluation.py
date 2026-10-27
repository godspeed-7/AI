"""Shared helpers for evals/ and experiments/: load the evaluation
questions and score what the retriever returned.

In:  ams-data/evaluation_questions.csv; the Documents retrieved for a
     question.
Out: load_questions() -> the CSV rows; score() -> one question's hit,
     recall and reciprocal rank; summarize() -> Hit Rate, Recall, MRR;
     print_comparison() -> an experiment's report vs the baseline.

Strategy: every script scores with these same functions, so a
difference between two runs comes from the retrieval, not the maths.
Metrics are computed as in basic-rag/evals/evaluate_retrieval.py.

Caveats:
- Chunks carry no section number, so a chunk's sections are read from
  the heading lines in its text ("4.1 Standard carry-over limit"). A
  chunk with no heading line never counts as a hit.
"""

import csv
import re

from langchain_core.documents import Document

from ams_assistant.config import EVALUATION_FILE


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


def score(expected: set[str], docs: list[Document]) -> dict:
    """Score one question's retrieved chunks (in rank order).

    hit     at least one expected section was retrieved
    recall  share of the expected sections retrieved (1 of 2 -> 0.5)
    rr      1 / rank of the first chunk with an expected section
            (1st -> 1.0, 2nd -> 0.5, none -> 0.0)
    """
    keys_per_chunk = [chunk_keys(doc) for doc in docs]
    matched = expected & set().union(*keys_per_chunk)

    rr = 0.0
    for rank, keys in enumerate(keys_per_chunk, start=1):
        if keys & expected:
            rr = 1 / rank
            break

    return {
        "hit": bool(matched),
        "recall": len(matched) / len(expected),
        "rr": rr,
        "keys_per_chunk": keys_per_chunk,
    }


def summarize(scores: list[dict]) -> dict:
    """Average per-question scores into Hit Rate (%), Recall and MRR."""
    total = len(scores)
    return {
        "hits": sum(s["hit"] for s in scores),
        "total": total,
        "hit_rate": sum(s["hit"] for s in scores) / total * 100,
        "recall": sum(s["recall"] for s in scores) / total,
        "mrr": sum(s["rr"] for s in scores) / total,
    }


def print_comparison(
    label: str,
    questions: list[dict],
    baseline: list[dict],
    experiment: list[dict],
    details: list[str],
) -> None:
    """Print baseline vs experiment metrics side by side, then every
    question whose hit/miss flipped, with its details (e.g. the
    rewritten query) so you can see why.

    baseline and experiment hold one score() result per question, in
    the same order as questions and details.
    """
    a = summarize(baseline)
    b = summarize(experiment)

    print(f"\n{'':10}{'Baseline':>12}{label:>12}{'Change':>10}")
    print(
        f"{'Hit Rate':10}{a['hit_rate']:>11.2f}%{b['hit_rate']:>11.2f}%"
        f"{b['hit_rate'] - a['hit_rate']:>+9.2f}%"
    )
    for name, key in (("Recall", "recall"), ("MRR", "mrr")):
        print(f"{name:10}{a[key]:>12.4f}{b[key]:>12.4f}{b[key] - a[key]:>+10.4f}")

    rows = list(zip(questions, baseline, experiment, details))
    fixed = [r for r in rows if not r[1]["hit"] and r[2]["hit"]]
    broken = [r for r in rows if r[1]["hit"] and not r[2]["hit"]]

    for title, group in (("Fixed (miss -> hit)", fixed),
                         ("Broken (hit -> miss)", broken)):
        print(f"\n{title}: {len(group)}")

        for item, _before, _after, detail in group:
            print(f"\n  Question : {item['question']}")
            print(f"  {label:9}: {detail}")
            print(f"  Expected : {item['expected_source']}")
