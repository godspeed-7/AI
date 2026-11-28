"""How often the LLM judge agrees with a person.

In:  uv run python evals/calibrate_judge.py (reads evals/judge_key.csv,
     ~20 answers a person graded).
Out: the judge's verdict on each, the disagreements, the agreement rate.

How: test the judge on graded answers before trusting its grades.

Watch out: about 20 judge calls (Gemma's own quota).
"""

import csv
import sys

from ams_agent import judge
from ams_agent.config import JUDGE_KEY, QUESTIONS


def main() -> None:
    with QUESTIONS.open(newline="", encoding="utf-8") as f:
        questions = {q["id"]: q for q in csv.DictReader(f)}
    with JUDGE_KEY.open(newline="", encoding="utf-8") as f:
        key = list(csv.DictReader(f))
    if not key:
        sys.exit(f"{JUDGE_KEY} has no graded answers yet: add ~20.")
    agree = 0
    for row in key:
        q = questions[row["question_id"]]
        verdict = judge.grade(q["question"], q["expected_answer"],
                              row["answer"])
        person = row["correct"].strip().lower() == "yes"
        same = verdict is not None and verdict.correct == person
        agree += same
        mark = "✅" if same else "❌"
        said = "no verdict" if verdict is None else (
            f"judge {'yes' if verdict.correct else 'no'}: {verdict.reason}")
        print(f"{mark} {row['question_id']} person "
              f"{'yes' if person else 'no'} · {said}")
    print(f"\nAgreement: {agree} / {len(key)} ({agree / len(key):.0%})")


if __name__ == "__main__":
    main()
