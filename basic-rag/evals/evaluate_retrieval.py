
import csv
import re

from basic_rag.config import EVALUATION_FILE, TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import get_client, search
from basic_rag.logger import heading, progress, success, info, error


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    # Extract IDs such as 3.1, 4.3, or top-level IDs such as 5.
    return set(re.findall(r"\d+(?:\.\d+)*", expected_source))


def main():
    heading("RAG RETRIEVAL EVALUATION")

    questions = load_questions(EVALUATION_FILE)
    client = get_client()

    total = len(questions)
    hits = 0
    recall_sum = 0.0
    mrr_sum = 0.0
    failures = []

    info(f"Evaluation questions: {total}")
    info(f"Retrieving top {TOP_K} chunks per question")

    for index, item in enumerate(questions, start=1):
        question = item["question"]
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        progress(f"[{index}/{total}] {question}")

        question_embedding = generate_embedding(question)

        results = search(client, question_embedding, limit=TOP_K)

        # Preserve ranking order for MRR.
        retrieved_ids = [
            point.payload.get("section_id", "").strip()
            for point in results
            if point.payload
            and point.payload.get("section_id", "").strip()
        ]

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
