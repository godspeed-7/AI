"""Answer evaluation: run the full pipeline and grade every answer.

In:  every question in ams-data/evaluation_questions.csv (unanswerable
     ones included: for those, "I can't tell from the policies" is the
     right answer).
Out: evals/answer_evaluation_results[_reranked].csv (one row per
     question, written as the run goes) and the average scores, overall
     and per category. Compare with basic-rag's 92.7%.

Strategy: per question, build_chain() answers it (same pipeline as
query.py), then the judge (judge.py) scores the answer 0-2 on
correctness, context_support and completeness, i.e. 0-6 in total.

Usage (from ams-assistant/):
    uv run python evals/evaluate_answers.py --limit 5   # quick check
    uv run python evals/evaluate_answers.py             # full run
    uv run python evals/evaluate_answers.py --rerank    # with reranker

Caveats:
- Slow: two LLM calls per question, about an hour for the full set.
- The results file is overwritten on every run.
- A question that fails (e.g. a judge reply that doesn't fit Scores)
  is logged and skipped, so a long run isn't lost.
"""

import argparse
import csv
from collections import defaultdict

from ams_assistant.chain import build_chain
from ams_assistant.config import EVALS_DIR
from ams_assistant.evaluation import load_questions
from ams_assistant.judge import build_judge
from ams_assistant.prompts import format_docs


FIELDNAMES = [
    "question",
    "category",
    "expected_answer",
    "expected_source",
    "retrieved_sources",
    "generated_answer",
    "correctness",
    "context_support",
    "completeness",
    "total_score",
    "explanation",
]


def main():
    """Answer and grade every question, then print the averages."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rerank", action="store_true",
                        help="retrieve with the cross-encoder reranker")
    parser.add_argument("--limit", type=int,
                        help="only the first N questions (a quick check)")
    args = parser.parse_args()

    questions = load_questions()[:args.limit]
    chain = build_chain(use_reranker=args.rerank)
    judge = build_judge()

    suffix = "_reranked" if args.rerank else ""
    output_file = EVALS_DIR / f"answer_evaluation_results{suffix}.csv"
    rows = []
    failed = []

    with open(output_file, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()

        for index, item in enumerate(questions, start=1):
            question = item["question"]
            print(f"[{index}/{len(questions)}] {question}")

            try:
                result = chain.invoke(question)
                answer = result["answer"].content
                scores = judge.invoke({
                    "question": question,
                    "expected_answer": item["expected_answer"],
                    # The judge sees the same chunks the answerer saw.
                    "retrieved_context": format_docs(result["docs"]),
                    "generated_answer": answer,
                })
            except Exception as error:
                print(f"    FAILED: {error}")
                failed.append(question)
                continue

            print(f"    {scores.total}/6  {answer[:100]}")

            row = {
                "question": question,
                "category": item["category"],
                "expected_answer": item["expected_answer"],
                "expected_source": item["expected_source"],
                "retrieved_sources": "; ".join(
                    doc.metadata["source"] for doc in result["docs"]
                ),
                "generated_answer": answer,
                "correctness": scores.correctness,
                "context_support": scores.context_support,
                "completeness": scores.completeness,
                "total_score": scores.total,
                "explanation": scores.explanation,
            }
            rows.append(row)
            writer.writerow(row)
            file.flush()  # keep the file current during a long run

    print_summary(rows, failed)
    print(f"\nPer-question results: {output_file}")


def print_summary(rows: list[dict], failed: list[str]) -> None:
    """Print the average scores, overall and per category."""
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

    # defaultdict(list) creates an empty list for a new category.
    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row["total_score"])

    print("\nBy category:")
    for category, totals in sorted(by_category.items()):
        percent = sum(totals) / (6 * len(totals)) * 100
        print(f"  {category:14} {percent:5.1f}%  ({len(totals)} questions)")


if __name__ == "__main__":
    main()
