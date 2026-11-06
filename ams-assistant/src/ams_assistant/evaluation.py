"""Shared helpers for evals/ and experiments/: load the evaluation
questions and score what the retriever returned.

In:  ams-data/evaluation_questions.csv; the Documents retrieved for a
     question.
Out: load_questions() -> the CSV rows; score() -> one question's hit,
     recall and reciprocal rank; summarize() -> Hit Rate, Recall, MRR;
     print_comparison() -> an experiment's report vs the baseline;
     compare() -> runs pipelines (pipeline.py) and prints that report.

Strategy: every script scores with these same functions, so a
difference between two runs comes from the retrieval, not the maths.
Metrics are computed as in basic-rag/evals/evaluate_retrieval.py.

Caveats:
- A chunk's sections are read from the heading lines in its text
  ("4.1 Standard carry-over limit"), since one chunk can hold several
  (its subsections, a merged short section). A chunk with no heading
  line never counts as a hit.
- The handbooks repeat some facts in several chapters. The CSV's
  also_correct column lists, per expected section, other sections that
  state the same answer; finding one of those counts as finding it.
"""

import csv
import re

from langchain_core.documents import Document

from ams_assistant.config import EVALUATION_FILE
from ams_assistant.pipeline import Pipeline, search_and_rerank, transform


# Same heading rule as basic-rag's chunker: a line starting with a
# number like "4." or "4.1" followed by a title.
HEADING_PATTERN = re.compile(r"(?m)^[ \t]*(\d+(?:\.\d+)*)\.?[ \t]+\S")


def load_questions() -> list[dict]:
    """Read the CSV; each row is a dict with keys question,
    expected_answer, expected_source, category, split, department, and
    also_correct."""
    with open(EVALUATION_FILE, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def split_list(text: str) -> list[str]:
    """Turn "a; b" into ["a", "b"]."""
    return [part.strip() for part in text.split(";") if part.strip()]


def expected_groups(item: dict) -> list[set[str]]:
    """Return one set per expected section: the section itself plus its
    alternatives from also_correct ("expected=alternative" pairs).

    expected_source "a.txt#4.1; b.txt#2" with also_correct
    "a.txt#4.1=c.txt#3.2" -> [{"a.txt#4.1", "c.txt#3.2"}, {"b.txt#2"}]
    """
    groups = {key: {key} for key in split_list(item["expected_source"])}

    for pair in split_list(item.get("also_correct", "")):
        key, alternative = (part.strip() for part in pair.split("="))
        groups[key].add(alternative)

    return list(groups.values())


def chunk_keys(doc: Document) -> set[str]:
    """Return the "document#section" keys of every heading in a chunk,
    or an empty set if it has none."""
    source = doc.metadata["source"]
    return {
        f"{source}#{number}"
        for number in HEADING_PATTERN.findall(doc.page_content)
    }


def score(expected: list[set[str]], docs: list[Document]) -> dict:
    """Score one question's retrieved chunks (in rank order). expected
    comes from expected_groups(): a section counts as found when it, or
    one of its alternatives, was retrieved.

    hit     at least one expected section was found
    recall  share of the expected sections found (1 of 2 -> 0.5)
    rr      1 / rank of the first chunk with an expected section
            (1st -> 1.0, 2nd -> 0.5, none -> 0.0)
    """
    keys_per_chunk = [chunk_keys(doc) for doc in docs]
    retrieved = set().union(*keys_per_chunk)
    found = [group for group in expected if group & retrieved]
    any_expected = set().union(*expected)

    rr = 0.0
    for rank, keys in enumerate(keys_per_chunk, start=1):
        if keys & any_expected:
            rr = 1 / rank
            break

    return {
        "hit": bool(found),
        "recall": len(found) / len(expected),
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


# Lines that ingestion-side experiments add to a chunk's text.
ADDED_LINE_PREFIXES = ("Context: ", "Glossary: ")


def describe(question: str, text: str, docs: list[Document]) -> str:
    """One flipped question's details: the text it was searched with
    (if changed), the top chunk, and why that chunk came up."""
    top = docs[0]
    parts = []
    if text != question:
        parts.append(f'searched "{text}"')
    parts.append(f"top = {top.metadata['source']}#{top.metadata['section']}")
    parts += [line for line in top.page_content.splitlines()
              if line.startswith(ADDED_LINE_PREFIXES)]
    if "matched_via" in top.metadata:
        parts.append(f'matched via "{top.metadata["matched_via"]}"')
    return "\n             ".join(parts)


def compare(baseline: Pipeline, candidates: dict[str, Pipeline]) -> None:
    """Run the baseline and every candidate on the answerable questions,
    then print each candidate against the baseline. Labels (the keys)
    should be at most 10 characters to fit the table."""
    items = [q for q in load_questions() if q["expected_source"].strip()]
    questions = [item["question"] for item in items]

    def run(label: str, pipeline: Pipeline) -> tuple[list[dict], list[str]]:
        print(f"Running {label}: {pipeline}", flush=True)
        texts = transform(questions, pipeline)
        found = search_and_rerank(texts, pipeline)
        changed = sum(t != q for t, q in zip(texts, questions))
        if changed:
            print(f"  search text changed for {changed}/{len(texts)}")
        scores = [score(expected_groups(item), docs)
                  for item, docs in zip(items, found)]
        details = [describe(q, t, docs)
                   for q, t, docs in zip(questions, texts, found)]
        return scores, details

    baseline_scores, _details = run("baseline", baseline)
    for label, pipeline in candidates.items():
        scores, details = run(label, pipeline)
        print(f"\n=== {label} ===")
        print_comparison(label, items, baseline_scores, scores, details)
