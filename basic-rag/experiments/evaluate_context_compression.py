"""Experiment: does compressing the retrieved context help the answers?

For every question in ams-data/evaluation_questions.csv, retrieve the
TOP_K chunks once, then for each strategy in STRATEGIES (see
basic_rag/compressor.py):
    1. Compress the context (none = unchanged, the baseline).
    2. Answer with the real prompt (prompts.build_prompt_from_context).
    3. Grade the answer with the shared judge (basic_rag/judge.py).
Every strategy gets the same chunks, so only the compression differs.

Out: experiments/context_compression_results.csv (one row per question
     and strategy, written as the run goes) and, per strategy, the
     average score, context reduction, and compression/answer time.

Caveats:
- Slow: up to 3 LLM calls per question and strategy (compress, answer,
  judge); roughly 1.5-2 hours for the full set.
- With TOP_K = 3 the context is short (median ~670 characters), so
  extractive often keeps everything and there is little to compress.
- The judge checks context_support against the compressed context, so
  a fact lost or distorted by compression isn't caught there (only via
  correctness against the reference answer).
- A question that fails (e.g. the judge returns bad JSON) is logged
  and skipped, so a long run isn't lost.
"""

import csv
import time

from basic_rag.compressor import compress_context
from basic_rag.config import EVALUATION_FILE, EXPERIMENTS_DIR, TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer
from basic_rag.judge import judge_answer
from basic_rag.logger import error, heading, info, progress, success
from basic_rag.prompts import build_prompt_from_context, format_context
from basic_rag.vector_store import get_client, search


# Strategies to compare; "none" is the baseline.
STRATEGIES = ["none", "extractive", "abstractive"]
# How many sentences the extractive strategy keeps.
KEEP_SENTENCES = 6

# One row per question and strategy; overwritten on every run.
OUTPUT_FILE = EXPERIMENTS_DIR / "context_compression_results.csv"

FIELDNAMES = [
    "question",
    "expected_answer",
    "expected_source",
    "strategy",
    "retrieved_sections",
    "original_context_chars",
    "compressed_context_chars",
    "context_reduction_percent",
    "compression_seconds",
    "generation_seconds",
    "correctness",
    "context_support",
    "completeness",
    "total_score",
    "judge_explanation",
    "generated_answer",
    "original_context",
    "compressed_context",
]


def load_questions(file_path) -> list[dict]:
    """Read the evaluation CSV into a list of row dicts."""
    with open(file_path, "r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def retrieve(client, question: str) -> list:
    """Embed the question and return its TOP_K nearest chunks."""
    return search(client, generate_embedding(question), limit=TOP_K)


def run_strategy(
    item: dict,
    original_context: str,
    retrieved_sections: str,
    strategy: str,
) -> dict:
    """Compress, answer, and judge one question with one strategy.

    Returns one result row (see FIELDNAMES).
    """
    question = item["question"].strip()
    expected_answer = item["expected_answer"].strip()

    # Step 1: compress, timed separately from answering.
    compression_start = time.perf_counter()
    compressed_context = compress_context(
        question=question,
        context=original_context,
        strategy=strategy,
        keep_sentences=KEEP_SENTENCES,
    )
    compression_seconds = time.perf_counter() - compression_start

    # Step 2: answer with the real prompt.
    prompt = build_prompt_from_context(question, compressed_context)
    generation_start = time.perf_counter()
    generated_answer = generate_answer(prompt)
    generation_seconds = time.perf_counter() - generation_start

    # Step 3: judge against the context the answerer actually saw.
    evaluation = judge_answer(
        question=question,
        expected_answer=expected_answer,
        generated_answer=generated_answer,
        retrieved_context=compressed_context,
    )

    original_chars = len(original_context)
    compressed_chars = len(compressed_context)
    reduction_percent = (
        (original_chars - compressed_chars) / original_chars * 100
        if original_chars
        else 0.0
    )

    return {
        "question": question,
        "expected_answer": expected_answer,
        "expected_source": item.get("expected_source", "").strip(),
        "strategy": strategy,
        "retrieved_sections": retrieved_sections,
        "original_context_chars": original_chars,
        "compressed_context_chars": compressed_chars,
        "context_reduction_percent": round(reduction_percent, 2),
        "compression_seconds": round(compression_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "correctness": evaluation["correctness"],
        "context_support": evaluation["context_support"],
        "completeness": evaluation["completeness"],
        "total_score": evaluation["total_score"],
        "judge_explanation": evaluation["explanation"],
        "generated_answer": generated_answer,
        "original_context": original_context,
        "compressed_context": compressed_context,
    }


def print_summary(rows: list[dict]):
    """Print, per strategy, the average score, reduction, and times."""
    heading("CONTEXT COMPRESSION SUMMARY")

    for strategy in STRATEGIES:
        strategy_rows = [r for r in rows if r["strategy"] == strategy]

        if not strategy_rows:
            continue

        count = len(strategy_rows)

        def average(field: str) -> float:
            return sum(r[field] for r in strategy_rows) / count

        print(f"\nStrategy: {strategy}")
        print(f"  Questions evaluated      : {count}")
        print(f"  Average answer score     : {average('total_score'):.2f}/6")
        print(
            "  Average context reduction: "
            f"{average('context_reduction_percent'):.2f}%"
        )
        print(
            "  Average compression time : "
            f"{average('compression_seconds'):.2f}s"
        )
        print(
            "  Average generation time  : "
            f"{average('generation_seconds'):.2f}s"
        )


def main():
    """Run every strategy on every question and compare them."""
    heading("RAG CONTEXT COMPRESSION EXPERIMENT")

    questions = load_questions(EVALUATION_FILE)
    info(f"Evaluation questions: {len(questions)}")
    info(f"Strategies: {', '.join(STRATEGIES)}")
    info(f"Retrieving top {TOP_K} chunks per question")

    client = get_client()
    rows = []

    # Rows are written as they're produced, so a crash late in a long
    # run still leaves everything finished before it on disk.
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()

            for index, item in enumerate(questions, start=1):
                question = item["question"].strip()
                progress(f"[{index}/{len(questions)}] {question}")

                try:
                    # Retrieve once, so every strategy gets the same
                    # chunks, with the same labels as query.py.
                    chunks = retrieve(client, question)
                    original_context = format_context(chunks)
                    retrieved_sections = "; ".join(
                        f"{p.payload.get('source', '')}#"
                        f"{p.payload.get('section_id', '')}"
                        for p in chunks
                        if p.payload
                    )

                    for strategy in STRATEGIES:
                        row = run_strategy(
                            item,
                            original_context,
                            retrieved_sections,
                            strategy,
                        )
                        rows.append(row)
                        writer.writerow(row)
                        file.flush()

                        print(
                            f"    {strategy:<11} "
                            f"score {row['total_score']}/6 | "
                            "reduction "
                            f"{row['context_reduction_percent']:.1f}% | "
                            f"compress {row['compression_seconds']:.2f}s"
                            f" | answer {row['generation_seconds']:.2f}s"
                        )

                except Exception as exc:
                    # Skip this question rather than lose the whole run.
                    error(f"Skipped question {index}: {exc}")

    finally:
        client.close()

    print_summary(rows)
    success(f"Detailed results saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
