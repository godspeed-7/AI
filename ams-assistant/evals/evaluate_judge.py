"""Judge evaluation: the judge checked against a person
(EVAL_PLAYBOOK.md, D5).

In:  ams-data/agent_judge_key.csv: one agent run's replies as the judge
     saw them (evaluate_agent.py --judge-key), each marked by a person
     0-2 on correctness, context_support and completeness, by
     judge_prompt.txt's rules, with a note if they like.
Out: per mark, how often the judge gave the person's mark, and when it
     didn't, whether it was kinder or stricter; then each disagreement
     with both marks, the person's note and the judge's reason.

Strategy: the judge (judge.py) grades each marked reply again from the
key's own columns, so the key doesn't depend on a later run. Its
grades are cached: a rerun is free until judge_prompt.txt or the judge
changes, and then shows whether the change agrees with the person more
(a regression test for the judge, D2).

Usage (from ams-assistant/):
    uv run python evals/evaluate_judge.py

Caveats:
- A row without all three marks is skipped and counted, so a key can be
  checked half done.
- The marks belong to one run's replies: after the agent changes, make
  a new key (delete the file, then evaluate_agent.py --judge-key).
- A grade that fails (judge.py's Caveats) is listed, not compared.
"""

import csv
import sys

import httpx
from openai import OpenAIError

from ams_assistant.config import (
    AGENT_JUDGE_KEY_FILE,
    JUDGE_MODEL,
    JUDGE_PROVIDER,
)
from ams_assistant.judge import BROKEN_REPLY, Scores, build_judge

MARKS = ("correctness", "context_support", "completeness")


def read_key() -> tuple[list[dict], list[str]]:
    """The key's rows with all three marks (as numbers), and the IDs of
    the rest. Stops with a message at a mark that isn't 0, 1 or 2."""
    with open(AGENT_JUDGE_KEY_FILE, encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    marked, unmarked = [], []
    for row in rows:
        marks = [row[mark].strip() for mark in MARKS]
        if not all(marks):
            unmarked.append(row["id"])
        elif set(marks) <= {"0", "1", "2"}:
            marked.append(row | dict(zip(MARKS, map(int, marks),
                                         strict=True)))
        else:
            sys.exit(f"{row['id']}: a mark must be 0, 1 or 2, not "
                     f"{', '.join(marks)}")
    return marked, unmarked


def grade(rows: list[dict]) -> tuple[list[tuple[dict, Scores]],
                                     list[str]]:
    """The judge's grade for each row, from the key's columns; and the
    rows it failed to grade, with why."""
    judge = build_judge()
    graded, failed = [], []
    for number, row in enumerate(rows, start=1):
        print(f"[{number}/{len(rows)}] {row['id']}", end="\r")
        try:
            graded.append((row, judge.invoke({
                "question": row["question"],
                "expected_answer": row["expected_answer"],
                "retrieved_context": row["context"],
                "generated_answer": row["generated_answer"],
            })))
        except (*BROKEN_REPLY, OpenAIError, httpx.HTTPError) as error:
            # A broken reply, or the model's service failing: keep
            # going, and list it at the end.
            failed.append(f"{row['id']} ({error})")
    return graded, failed


def print_agreement(graded: list[tuple[dict, Scores]]) -> None:
    """Per mark: the judge gave the person's mark, or was kinder or
    stricter; then every reply where they differ."""
    print(f"\nJudge ({JUDGE_PROVIDER} {JUDGE_MODEL}) vs the person, "
          f"{len(graded)} replies:")
    for mark in MARKS:
        pairs = [(row[mark], getattr(scores, mark))
                 for row, scores in graded]
        agreed = sum(person == judge for person, judge in pairs)
        kinder = sum(judge > person for person, judge in pairs)
        print(f"  {mark:16}: agreed {agreed}/{len(pairs)} · judge kinder "
              f"{kinder}, stricter {len(pairs) - agreed - kinder}")
    differ = [(row, scores) for row, scores in graded
              if any(row[mark] != getattr(scores, mark) for mark in MARKS)]
    print(f"  {'all three':16}: agreed {len(graded) - len(differ)}/"
          f"{len(graded)}")
    if differ:
        print("\nWhere they differ (person → judge):")
    for row, scores in differ:
        marks = " · ".join(f"{mark} {row[mark]} → {getattr(scores, mark)}"
                           for mark in MARKS
                           if row[mark] != getattr(scores, mark))
        print(f"  {row['id']:4} {marks}")
        if row["note"].strip():
            print(f"       person: {row['note'].strip()}")
        print(f"       judge : {scores.explanation}")


def main():
    if not AGENT_JUDGE_KEY_FILE.exists():
        sys.exit(f"No hand key yet ({AGENT_JUDGE_KEY_FILE}): make it with "
                 f"evals/evaluate_agent.py --judge-key, then mark it")
    rows, unmarked = read_key()
    if unmarked:
        print(f"Not marked yet, skipped: {', '.join(unmarked)}")
    if not rows:
        sys.exit("Nothing to compare: mark correctness, context_support "
                 "and completeness (0-2) for each reply first")
    graded, failed = grade(rows)
    print_agreement(graded)
    if failed:
        print(f"\nThe judge failed on (not compared): {'; '.join(failed)}")


if __name__ == "__main__":
    main()
