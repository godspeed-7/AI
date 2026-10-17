import time

from qdrant_client import QdrantClient

from basic_rag.config import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    LLM_MODEL,
    QDRANT_URL,
    TOP_K,
)
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer
from basic_rag.prompts import build_prompt
from basic_rag.logger import (
    info,
    progress,
    success,
    heading,
    timing,
    error,
)


def main():
    start_time = time.perf_counter()
    client = None

    heading("HR POLICY RAG SYSTEM")

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

        # Important: Do not call create_vector_store() here.
        # That function deletes and recreates the collection.
        client = QdrantClient(url=QDRANT_URL)

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=question_embedding,
            limit=TOP_K,
            with_payload=True,
        ).points

        success(f"Retrieved {len(results)} relevant chunks")
        print("\n--- RETRIEVED CONTEXT ---")

        for i, point in enumerate(results, start=1):
            payload = point.payload or {}
            print(f"\n[Chunk {i}]")
            print(f"Section: {payload.get('section_title')}")
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

    except Exception as exc:
        error(f"RAG query failed: {exc}")

    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
