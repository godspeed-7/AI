"""What a person should look at, and turning it into a test.

In:  uv run python evals/review_queue.py [--days 1]
     uv run python evals/review_queue.py --to-test 42
Out: the queue: answers with a thumbs-down, answers an online check
     flagged, and REVIEW_SAMPLE random others a day; --to-test drafts a
     new test case from answer 42 into evals/candidates.csv.

Strategy: close the loop: a real failure -> a person reviews it -> a
new test case -> fix -> run again. The random sample catches what no
check flags. A drafted case still needs its right answer and checks,
written by the person; it joins evals/questions.csv only then, so the
golden set never holds a guess.

Caveats: reads data/quality.sqlite, which holds what was asked and
answered: for reviewers only.
"""

import argparse
import csv
import json
import random
from contextlib import closing
from datetime import datetime, timedelta

from ams_agent.config import CANDIDATES, QUESTIONS, REVIEW_SAMPLE
from ams_agent.quality import connect


def queue(days: int) -> list[dict]:
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with closing(connect()) as con:
        con.row_factory = lambda c, r: dict(
            zip([d[0] for d in c.description], r))
        rows = con.execute("SELECT * FROM answers WHERE at >= ? ORDER BY id",
                           (since,)).fetchall()
    picked = [r for r in rows if r["thumbs"] == 0 or json.loads(r["flags"])]
    rest = [r for r in rows if r not in picked]
    sample = random.sample(rest, min(REVIEW_SAMPLE * days, len(rest)))
    return [{**r, "why": "thumbs down" if r["thumbs"] == 0 else
             ", ".join(json.loads(r["flags"]))} for r in picked] + \
        [{**r, "why": "random sample"} for r in sample]


def to_test(row_id: int) -> None:
    with closing(connect()) as con:
        row = con.execute("SELECT at, employee_id, question FROM answers"
                          " WHERE id = ?", (row_id,)).fetchone()
    if not row:
        raise SystemExit(f"no answer #{row_id}")
    with QUESTIONS.open(newline="", encoding="utf-8") as f:
        fields = csv.DictReader(f).fieldnames
    new = not CANDIDATES.exists()
    with CANDIDATES.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow({k: "" for k in fields} | {
            "id": f"C{row_id}", "employee_id": row[1], "question": row[2],
            "expected_answer": "TO WRITE: the right answer, from the data",
            "check": "from review", "source": f"live answer #{row_id}"
            f" ({row[0][:10]})"})
    print(f"Drafted C{row_id} in {CANDIDATES}: write its right answer and"
          " checks, then move it into evals/questions.csv.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--to-test", type=int, metavar="ID")
    args = parser.parse_args()
    if args.to_test:
        to_test(args.to_test)
        return
    items = queue(args.days)
    for r in items:
        print(f"#{r['id']} {r['at']} {r['employee_id']} · {r['why']}\n"
              f"   Q: {r['question'][:200]}\n   A: {r['answer'][:300]}"
              + (f"\n   comment: {r['comment']}" if r["comment"] else ""))
    print(f"\n{len(items)} to review (last {args.days} day(s)).")


if __name__ == "__main__":
    main()
