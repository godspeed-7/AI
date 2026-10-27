"""Answer-quality evaluation: run the full pipeline and grade each answer.

For every question in ams-data/evaluation_questions.csv, retrieve the
chunks and generate an answer (same as query.py). Then a judge LLM
compares that answer with the expected answer and the retrieved chunks,
and scores it 0-2 on correctness, context_support, and completeness.

Out: evals/answer_evaluation_results.csv (one row per question) and
     the average scores.

Caveats:
- Slow: two LLM calls per question, about an hour for the full set.
- The results file is overwritten on every run.
- The judge is the same small model as the answerer (gemma3:4b), so
  treat small score differences as noise.
"""

import csv
from pathlib import Path

from basic_rag.config import EVALS_DIR, EVALUATION_FILE, TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer
from basic_rag.judge import judge_answer
from basic_rag.prompts import build_prompt
from basic_rag.vector_store import get_client, search


# Per-question results; overwritten on every run.
OUTPUT_FILE = EVALS_DIR / "answer_evaluation_results.csv"


def load_questions(file_path: Path) -> list[dict]:
    """Load evaluation questions from the CSV file."""
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def main():
    """Run the answer-quality evaluation."""

    print("=" * 60)
    print("RAG ANSWER-QUALITY EVALUATION")
    print("=" * 60)

    questions = load_questions(EVALUATION_FILE)
    client = get_client()
    results_for_report = []

    try:
        for index, item in enumerate(questions, start=1):
            question = item["question"].strip()
            expected_answer = item["expected_answer"].strip()
            expected_source = item.get("expected_source", "").strip()

            print(f"\n[{index}/{len(questions)}] {question}")

            # Step 1: Generate the question embedding.
            question_embedding = generate_embedding(question)

            # Step 2: Retrieve the top K chunks from Qdrant.
            retrieved_chunks = search(
                client, question_embedding, limit=TOP_K
            )

            # Kept for the judge and the CSV report.
            retrieved_context = "\n\n".join(
                point.payload.get("text", "")
                for point in retrieved_chunks
                if point.payload
            )

            # As "document#section", e.g. "leave_policy_us.txt#4.1", to
            # compare with the expected_source column in the report.
            retrieved_sections = [
                f"{point.payload.get('source', '')}#"
                f"{point.payload.get('section_id', '')}"
                for point in retrieved_chunks
                if point.payload
            ]

            # Step 3: Generate the answer using the shared prompt.
            prompt = build_prompt(question, retrieved_chunks)
            generated_answer = generate_answer(prompt)

            # Step 4: Evaluate the generated answer with the LLM judge.
            evaluation = judge_answer(
                question=question,
                expected_answer=expected_answer,
                generated_answer=generated_answer,
                retrieved_context=retrieved_context,
            )

            print(f"Generated answer: {generated_answer}")
            print(
                "Scores: "
                f"Correctness={evaluation['correctness']}/2, "
                f"Context support={evaluation['context_support']}/2, "
                f"Completeness={evaluation['completeness']}/2, "
                f"Total={evaluation['total_score']}/6"
            )
            print(f"Judge explanation: {evaluation['explanation']}")

            # Step 5: Keep everything about this question for the CSV.
            results_for_report.append(
                {
                    "question": question,
                    "expected_answer": expected_answer,
                    "expected_source": expected_source,
                    "retrieved_sections": "; ".join(retrieved_sections),
                    "retrieved_context": retrieved_context,
                    "generated_answer": generated_answer,
                    "correctness": evaluation["correctness"],
                    "context_support": evaluation["context_support"],
                    "completeness": evaluation["completeness"],
                    "total_score": evaluation["total_score"],
                    "judge_explanation": evaluation["explanation"],
                }
            )

    finally:
        client.close()

    # Save detailed results (one row per question; columns in this order).
    fieldnames = [
        "question",
        "expected_answer",
        "expected_source",
        "retrieved_sections",
        "retrieved_context",
        "generated_answer",
        "correctness",
        "context_support",
        "completeness",
        "total_score",
        "judge_explanation",
    ]

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results_for_report)

    # Print the overall summary.
    total = len(results_for_report)

    if total:
        correctness_avg = sum(
            row["correctness"] for row in results_for_report
        ) / total
        context_avg = sum(
            row["context_support"] for row in results_for_report
        ) / total
        completeness_avg = sum(
            row["completeness"] for row in results_for_report
        ) / total
        total_avg = sum(
            row["total_score"] for row in results_for_report
        ) / total
        # Summing booleans counts the True values.
        perfect_answers = sum(
            row["total_score"] == 6 for row in results_for_report
        )

        print("\n" + "=" * 60)
        print("ANSWER-QUALITY EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Questions evaluated    : {total}")
        print(f"Average correctness    : {correctness_avg:.2f}/2")
        print(f"Average context support: {context_avg:.2f}/2")
        print(f"Average completeness   : {completeness_avg:.2f}/2")
        print(f"Average total score    : {total_avg:.2f}/6")
        print(f"Perfect answers (6/6)  : {perfect_answers}/{total}")
        print(f"Overall percentage     : {total_avg / 6 * 100:.1f}%")

    print(f"\nDetailed report saved to:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
