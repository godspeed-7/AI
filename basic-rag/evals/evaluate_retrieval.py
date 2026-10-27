"""Baseline retrieval evaluation: does plain vector search find the
right policy section?

For every question in ams-data/evaluation_questions.csv, retrieve the
TOP_K chunks and compare them with the question's expected sections,
written as "document#section" (e.g. "leave_policy_us.txt#4.1"). No LLM
is involved, so it takes seconds. This is the baseline the other
retrieval experiments compare against.

Out: three metrics (all "@TOP_K"), plus the questions that missed:
    Hit Rate  % of questions where at least one expected section was
              retrieved.
    Recall    per question, the share of expected sections retrieved
              (1 of 2 -> 0.5), averaged.
    MRR       1 / rank of the first correct chunk (1st -> 1.0,
              2nd -> 0.5, none -> 0), averaged. Rewards ranking the
              right chunk first.

Caveats:
- Unanswerable questions (no expected section) are skipped; only
  evaluate_answers.py uses them.
- INTRODUCTION chunks have no section number, so they never count as
  a hit, even when they contain the answer.
"""

import csv

from basic_rag.config import EVALUATION_FILE, TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search
from basic_rag.logger import heading, progress, success, info, error


def load_questions(file_path: str) -> list[dict]:
    """Read the CSV; each row is a dict with keys question,
    expected_answer, expected_source, category, and split."""
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    """Turn "a.txt#4.1; b.txt#2" into {"a.txt#4.1", "b.txt#2"}."""
    return {
        key.strip() for key in expected_source.split(";") if key.strip()
    }


def section_key(point) -> str:
    """Return a retrieved point's "document#section" key, or "" if the
    chunk has no section (text before a document's first heading)."""
    payload = point.payload or {}
    section_id = str(payload.get("section_id", "")).strip()
    if not section_id:
        return ""
    return f"{payload.get('source', '')}#{section_id}"


def main():
    """Score vector search on every question and print the metrics."""
    heading("RAG RETRIEVAL EVALUATION")

    all_questions = load_questions(EVALUATION_FILE)
    # Only questions with an expected source can be scored.
    questions = [q for q in all_questions if q["expected_source"].strip()]
    client = get_client()

    # Running totals; divided by the question count at the end.
    total = len(questions)
    hits = 0
    recall_sum = 0.0
    mrr_sum = 0.0
    failures = []

    info(f"Evaluation questions: {total}")
    info(
        f"Skipped {len(all_questions) - total} questions with no "
        "expected source (unanswerable)"
    )
    info(f"Retrieving top {TOP_K} chunks per question")

    for index, item in enumerate(questions, start=1):
        question = item["question"]
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        progress(f"[{index}/{total}] {question}")

        # Steps 1-2: embed the question and retrieve the top chunks.
        question_embedding = generate_embedding(question)

        results = search(client, question_embedding, limit=TOP_K)

        # Step 3: score the result.
        # Preserve ranking order for MRR.
        retrieved_ids = [key for key in map(section_key, results) if key]

        retrieved_id_set = set(retrieved_ids)

        # Hit Rate: at least one expected section is retrieved.
        matched_ids = expected_ids & retrieved_id_set
        expected_section_found = bool(matched_ids)

        if expected_section_found:
            hits += 1
            success(f"Expected source found: {expected_source}")
        else:
            error(f"Expected source NOT found: {expected_source}")
            info(f"Expected IDs: {sorted(expected_ids)}")
            info(f"Retrieved IDs: {sorted(retrieved_id_set)}")

            failures.append({
                "question": question,
                "expected_source": expected_source,
                "expected_ids": sorted(expected_ids),
                "retrieved_ids": retrieved_ids,
                "retrieved_sections": sorted({
                    point.payload.get("section", "").strip()
                    for point in results
                    if point.payload
                }),
            })

        # Recall@3: proportion of expected sections retrieved.
        if expected_ids:
            question_recall = len(matched_ids) / len(expected_ids)
        else:
            question_recall = 0.0

        recall_sum += question_recall

        # MRR@3: reciprocal rank of the first expected section.
        reciprocal_rank = 0.0

        for rank, section_id in enumerate(retrieved_ids, start=1):
            if section_id in expected_ids:
                reciprocal_rank = 1.0 / rank
                break

        mrr_sum += reciprocal_rank

    # Average the per-question scores (guarding against an empty CSV).
    heading("RETRIEVAL EVALUATION SUMMARY")

    hit_rate = (hits / total * 100) if total else 0.0
    mean_recall = (recall_sum / total) if total else 0.0
    mrr = (mrr_sum / total) if total else 0.0

    print(f"Total questions : {total}")
    print(f"Source found    : {hits}")
    print(f"Source missing  : {total - hits}")
    print(f"Hit Rate@{TOP_K}   : {hit_rate:.2f}%")
    print(f"Recall@{TOP_K}      : {mean_recall:.4f} ({mean_recall * 100:.2f}%)")
    print(f"MRR@{TOP_K}         : {mrr:.4f}")

    if failures:
        heading("FAILED QUESTIONS")

        for index, failure in enumerate(failures, start=1):
            print(f"\n{index}. {failure['question']}")
            print(f"   Expected: {failure['expected_source']}")
            print(f"   Expected IDs: {failure['expected_ids']}")
            print(f"   Retrieved IDs: {failure['retrieved_ids']}")
            print(f"   Retrieved sections: {failure['retrieved_sections']}")


if __name__ == "__main__":
    main()
