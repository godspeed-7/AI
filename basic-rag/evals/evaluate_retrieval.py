
import csv
import re

from basic_rag.embedder import generate_embedding
from qdrant_client import QdrantClient
from basic_rag.vector_store import COLLECTION_NAME
from basic_rag.logger import heading, progress, success, info, error


EVALUATION_FILE = "documents/evaluation_questions.csv"
TOP_K = 3


def load_questions(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def extract_section_ids(expected_source: str) -> set[str]:
    # Extract IDs such as 3.1, 4.3, or top-level IDs such as 5.
    return set(
        re.findall(r"\d+(?:\.\d+)*", expected_source)
    )


def main():
    heading("RAG RETRIEVAL EVALUATION")

    questions = load_questions(EVALUATION_FILE)
    client = QdrantClient(url="http://localhost:6333")

    total = len(questions)
    hits = 0
    failures = []

    info(f"Evaluation questions: {total}")
    info(f"Retrieving top {TOP_K} chunks per question")

    for index, item in enumerate(questions, start=1):
        question = item["question"]
        expected_source = item["expected_source"].strip()
        expected_ids = extract_section_ids(expected_source)

        progress(f"[{index}/{total}] {question}")

        question_embedding = generate_embedding(question)

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=question_embedding,
            limit=TOP_K,
            with_payload=True,
        ).points

        retrieved_ids = {
            point.payload.get("section_id", "").strip()
            for point in results
            if point.payload.get("section_id", "").strip()
        }

        # A hit occurs when any expected section ID is retrieved.
        expected_section_found = bool(
            expected_ids & retrieved_ids
        )

        if expected_section_found:
            hits += 1
            success(f"Expected source found: {expected_source}")
        else:
            failures.append({
                "question": question,
                "expected_source": expected_source,
                "expected_ids": sorted(expected_ids),
                "retrieved_ids": sorted(retrieved_ids),
                "retrieved_sections": sorted({
                    point.payload.get("section", "").strip()
                    for point in results
                }),
            })

            error(f"Expected source NOT found: {expected_source}")
            info(f"Expected IDs: {sorted(expected_ids)}")
            info(f"Retrieved IDs: {sorted(retrieved_ids)}")

    heading("RETRIEVAL EVALUATION SUMMARY")

    hit_rate = (hits / total * 100) if total else 0

    print(f"Total questions : {total}")
    print(f"Source found    : {hits}")
    print(f"Source missing  : {total - hits}")
    print(f"Hit rate        : {hit_rate:.2f}%")

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
