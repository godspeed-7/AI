"""Answer evaluation: run the full pipeline and grade every answer.

In:  every question in ams-data/evaluation_questions.csv (unanswerable
     ones included: for those, "I can't tell from the policies" is the
     right answer).
Out: evals/answer_evaluation_results[_reranked].csv (one row per
     question, written as the run goes) and the average scores, overall,
     per category and per department.

Strategy: per question, build_chain() answers it (same pipeline as
query.py), then the judge (judge.py) scores the answer 0-2 on
correctness, context_support and completeness, i.e. 0-6 in total.
Each row also records whether retrieval found an expected section
(retrieval_hit, scored as in evaluate_retrieval.py), so a low score
can be traced to the search (no hit) or to the answer (hit).

Usage (from ams-assistant/):
    uv run python evals/evaluate_answers.py --limit 5   # quick check
    uv run python evals/evaluate_answers.py             # full run
    uv run python evals/evaluate_answers.py --rerank    # with reranker
    uv run python evals/evaluate_answers.py --workers 2 # 2 at a time

Caveats:
- Slow: two LLM calls per question, about two hours for the full set.
- --workers N grades N questions at the same time. Ollama only runs
  them at the same time if it was started with OLLAMA_NUM_PARALLEL=N;
  otherwise they queue and nothing gets faster.
- retrieval_hit is empty for unanswerable questions (nothing to find).
- The results file is overwritten on every run.
- A question that fails (e.g. a judge reply that doesn't fit Scores)
  is logged and skipped, so a long run isn't lost.
"""

import argparse
import csv
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from ams_assistant.chain import build_chain
from ams_assistant.config import EVALS_DIR
from ams_assistant.evaluation import expected_groups, load_questions, score
from ams_assistant.judge import build_judge
from ams_assistant.prompts import format_docs


FIELDNAMES = [
    "question",
    "category",
    "department",
    "expected_answer",
    "expected_source",
    "retrieved_sources",
    "retrieval_hit",
    "generated_answer",
    "correctness",
    "context_support",
    "completeness",
    "total_score",
    "explanation",
]


def grade(item: dict, chain, judge) -> dict:
    """Answer one question with the chain, grade the answer with the
    judge, and return its results row. Raises if either call fails."""
    question = item["question"]
    result = chain.invoke(question)
    answer = result["answer"].content
    scores = judge.invoke({
        "question": question,
        "expected_answer": item["expected_answer"],
        # The judge sees the same chunks the answerer saw.
        "retrieved_context": format_docs(result["docs"]),
        "generated_answer": answer,
    })

    hit = ""
    if item["expected_source"].strip():
        hit = score(expected_groups(item), result["docs"])["hit"]

    return {
        "question": question,
        "category": item["category"],
        "department": item["department"],
        "expected_answer": item["expected_answer"],
        "expected_source": item["expected_source"],
        "retrieved_sources": "; ".join(
            f"{doc.metadata['source']}#{doc.metadata['section']}"
            for doc in result["docs"]
        ),
        "retrieval_hit": hit,
        "generated_answer": answer,
        "correctness": scores.correctness,
        "context_support": scores.context_support,
        "completeness": scores.completeness,
        "total_score": scores.total,
        "explanation": scores.explanation,
    }


def main():
    """Answer and grade every question, then print the averages."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerank", action="store_true",
                        help="retrieve with the cross-encoder reranker")
    parser.add_argument("--limit", type=int,
                        help="only the first N questions (a quick check)")
    parser.add_argument("--workers", type=int, default=1,
                        help="questions graded at the same time (needs "
                             "OLLAMA_NUM_PARALLEL set to the same number)")
    args = parser.parse_args()

    questions = load_questions()[:args.limit]
    chain = build_chain(use_reranker=args.rerank)
    judge = build_judge()

    suffix = "_reranked" if args.rerank else ""
    output_file = EVALS_DIR / f"answer_evaluation_results{suffix}.csv"
    rows = []
    failed = []
    start = time.perf_counter()

    def safe_grade(item: dict) -> tuple[dict | None, Exception | None]:
        # Catch here: an error raised inside pool.map would stop the run.
        try:
            return grade(item, chain, judge), None
        except Exception as error:
            return None, error

    # Like Promise.all with a concurrency limit in JS: the pool runs up
    # to `workers` questions at once, and map returns the results in
    # question order.
    with (ThreadPoolExecutor(max_workers=args.workers) as pool,
          open(output_file, "w", encoding="utf-8", newline="") as file):
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        results = pool.map(safe_grade, questions)

        for index, (item, (row, error)) in enumerate(
            zip(questions, results), start=1
        ):
            print(f"[{index}/{len(questions)}] {item['question']}")

            if error is not None:
                print(f"    FAILED: {error}")
                failed.append(item["question"])
                continue

            print(f"    {row['total_score']}/6  "
                  f"{row['generated_answer'][:100]}")
            rows.append(row)
            writer.writerow(row)
            file.flush()  # keep the file current during a long run

    print_summary(rows, failed)
    minutes = (time.perf_counter() - start) / 60
    print(f"\nTook {minutes:.1f} minutes with {args.workers} worker(s)")
    print(f"Per-question results: {output_file}")


def print_summary(rows: list[dict], failed: list[str]) -> None:
    """Print the average scores, overall, per category and per
    department."""
    total = len(rows)
    if not total:
        print("\nNo questions were graded.")
        return

    print(f"\nGraded {total} questions ({len(failed)} failed)")

    for field in ("correctness", "context_support", "completeness"):
        average = sum(row[field] for row in rows) / total
        print(f"  {field:16}: {average:.2f}/2")

    average = sum(row["total_score"] for row in rows) / total
    perfect = sum(row["total_score"] == 6 for row in rows)
    print(f"  {'total':16}: {average:.2f}/6 = {average / 6 * 100:.1f}%")
    print(f"  {'perfect (6/6)':16}: {perfect}/{total}")

    for field in ("category", "department"):
        # defaultdict(list) creates an empty list for a new group.
        groups = defaultdict(list)
        for row in rows:
            groups[row[field]].append(row["total_score"])

        print(f"\nBy {field}:")
        for name, totals in sorted(groups.items()):
            percent = sum(totals) / (6 * len(totals)) * 100
            print(f"  {name:28} {percent:5.1f}%  ({len(totals)} questions)")


if __name__ == "__main__":
    main()
