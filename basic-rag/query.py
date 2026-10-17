"""Query pipeline: ask one question and get an answer from the AMS policy
documents.

Run from the basic-rag/ folder (after ingest.py has been run once):
    uv run python query.py

Steps:
    1. Embed      turn the question into a vector         (embedder.py)
    2. Retrieve   find the TOP_K most similar chunks      (vector_store.py)
    3. Prompt     combine question + chunks into a prompt (prompts.py)
    4. Generate   ask the LLM for the answer              (generator.py)

The retrieved chunks are printed before the answer, so you can see what
the model was given. This script only reads from Qdrant.

Needs Ollama and Qdrant running; see README.md.
"""

import time

from basic_rag.config import EMBEDDING_MODEL, LLM_MODEL, TOP_K
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer
from basic_rag.prompts import build_prompt
from basic_rag.vector_store import get_client, search
from basic_rag.logger import (
    info,
    progress,
    success,
    heading,
    timing,
    error,
)


def main():
    """Read a question, run the four query steps, and print the answer."""
    # Note: the timer starts before input(), so the total time also
    # includes how long you take to type the question.
    start_time = time.perf_counter()
    # Created in step 2; set to None first so `finally` can tell whether
    # there is a connection to close.
    client = None

    heading("AMS POLICY RAG SYSTEM")

    question = input("\nEnter your question: ").strip()

    if not question:
        error("Please enter a question.")
        return

    try:
        # Step 1: Generate the question embedding.
        progress(
            "[1/4] Generating question embedding using Ollama "
            f"({EMBEDDING_MODEL})..."
        )
        step_start = time.perf_counter()

        question_embedding = generate_embedding(question)

        success("Question embedding generated")
        timing(
            "Embedding generation",
            time.perf_counter() - step_start,
        )

        # Step 2: Retrieve relevant chunks from Qdrant.
        progress(
            "\n[2/4] Searching Qdrant for relevant chunks..."
        )
        step_start = time.perf_counter()

        client = get_client()
        results = search(client, question_embedding, limit=TOP_K)

        # Show exactly what the LLM will see. If the answer is wrong,
        # check here first: was the right section retrieved?
        success(f"Retrieved {len(results)} relevant chunks")
        print("\n--- RETRIEVED CONTEXT ---")

        for i, point in enumerate(results, start=1):
            payload = point.payload or {}
            print(f"\n[Chunk {i}]")
            print(f"Document: {payload.get('document_title')}")
            print(f"Section: {payload.get('section')}")
            print(payload.get("text", ""))

        print("\n--- END OF RETRIEVED CONTEXT ---")
        timing(
            "Qdrant retrieval",
            time.perf_counter() - step_start,
        )

        if not results:
            error(
                "No policy chunks were retrieved. "
                "Check the Qdrant collection and run ingestion "
                "if necessary."
            )
            return

        # Step 3: Build the prompt.
        progress(
            "\n[3/4] Building prompt with retrieved context..."
        )
        step_start = time.perf_counter()

        prompt = build_prompt(question, results)

        success("Prompt prepared")
        timing(
            "Prompt preparation",
            time.perf_counter() - step_start,
        )

        # Step 4: Generate the answer.
        progress(
            "\n[4/4] Generating answer using Ollama "
            f"({LLM_MODEL})..."
        )
        info("The model is generating your answer. Please wait...")

        step_start = time.perf_counter()

        answer = generate_answer(prompt)

        success("Answer generated")
        timing(
            "LLM generation",
            time.perf_counter() - step_start,
        )

        heading("RAG ANSWER")
        print(answer)

        total_time = time.perf_counter() - start_time
        print()
        timing("Total processing time", total_time)

    # Typical failures: Ollama or Qdrant not running, or a model
    # missing from Ollama.
    except Exception as exc:
        error(f"RAG query failed: {exc}")

    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
