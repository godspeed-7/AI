import csv
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from qdrant_client import QdrantClient

from basic_rag.config import (
    COLLECTION_NAME,
    EVALS_DIR,
    EVALUATION_FILE,
    JUDGE_MODEL,
    OLLAMA_GENERATE_URL,
    QDRANT_URL,
    TOP_K,
)
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer
from basic_rag.prompts import build_prompt


OUTPUT_FILE = EVALS_DIR / "answer_evaluation_results.csv"


def load_questions(file_path: Path) -> list[dict]:
    """Load evaluation questions from the CSV file."""
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def judge_answer(
    question: str,
    expected_answer: str,
    generated_answer: str,
    retrieved_context: str,
) -> dict:
    """Evaluate the generated answer against the reference and context."""

    judge_prompt = f"""
You are evaluating the quality of an answer produced by a RAG system
for an HR leave policy.

Evaluate the generated answer using the question, reference answer,
and retrieved policy context.

Scoring rules:

- correctness: Is the generated answer factually consistent with the
  reference answer? Score 0, 1, or 2.
- context_support: Are the claims in the generated answer supported by
  the retrieved context? Score 0, 1, or 2.
- completeness: Does the generated answer include the important details
  needed to answer the question, compared with the reference answer?
  Score 0, 1, or 2.

For all scores:
0 = Poor or incorrect
1 = Partially correct, supported, or complete
2 = Good, correct, supported, or complete

Important rules:

- Different wording is acceptable if the meaning is equivalent.
- Do not reward an answer for repeating the reference if the context
  contradicts or fails to support it.
- If the context does not contain enough information, an answer that
  appropriately says so can be correct.
- Do not assume facts that are absent from the context.
- Judge the answer against the actual question, not just keyword overlap.
- Do not penalize a concise answer when it contains all the details
  necessary to answer the question.
- If an answer contradicts itself, consider that in the correctness
  and completeness scores.
- Explain the scores briefly and objectively.

Return only valid JSON in this exact structure:
{{
  "correctness": 0,
  "context_support": 0,
  "completeness": 0,
  "explanation": "Brief explanation of the scores"
}}

Question:
{question}

Reference answer:
{expected_answer}

Retrieved policy context:
{retrieved_context}

Generated answer:
{generated_answer}
"""

    request_data = {
        "model": JUDGE_MODEL,
        "prompt": judge_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    request = Request(
        url=OLLAMA_GENERATE_URL,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=180) as response:
        response_data = json.loads(response.read().decode("utf-8"))

    judge_text = response_data["response"].strip()

    try:
        result = json.loads(judge_text)
    except json.JSONDecodeError:
        # Fallback if the model wraps JSON in additional text.
        match = re.search(r"\{.*\}", judge_text, re.DOTALL)
        if not match:
            raise ValueError(
                f"Judge did not return valid JSON: {judge_text}"
            )
        result = json.loads(match.group())

    score_fields = ("correctness", "context_support", "completeness")

    for field in score_fields:
        score = result.get(field)
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or score not in (0, 1, 2)
        ):
            raise ValueError(
                f"Invalid judge score for '{field}': {score!r}"
            )

    result["explanation"] = str(result.get("explanation", "")).strip()
    result["total_score"] = sum(result[field] for field in score_fields)

    return result


def main():
    """Run the answer-quality evaluation."""

    print("=" * 60)
    print("RAG ANSWER-QUALITY EVALUATION")
    print("=" * 60)

    questions = load_questions(EVALUATION_FILE)
    client = QdrantClient(url=QDRANT_URL)
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
            # Do not call create_vector_store() here because it
            # deletes and recreates the collection.
            retrieved_chunks = client.query_points(
                collection_name=COLLECTION_NAME,
                query=question_embedding,
                limit=TOP_K,
                with_payload=True,
            ).points

            retrieved_context = "\n\n".join(
                point.payload.get("text", "")
                for point in retrieved_chunks
                if point.payload
            )

            retrieved_sections = [
                point.payload.get("section_id", "")
                for point in retrieved_chunks
                if point.payload
            ]

            # Step 3: Generate the answer using the shared prompt.
            prompt = build_prompt(question, retrieved_chunks)
            generated_answer = generate_answer(prompt)

            # Step 4: Evaluate the generated answer.
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

            results_for_report.append(
                {
                    "question": question,
                    "expected_answer": expected_answer,
                    "expected_source": expected_source,
                    "retrieved_sections": ", ".join(retrieved_sections),
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

    # Save detailed results.
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
