
import time

from qdrant_client import QdrantClient

from basic_rag.embedder import generate_embedding
from basic_rag.vector_store import COLLECTION_NAME
from basic_rag.generator import generate_answer
from basic_rag.logger import (
    info,
    progress,
    success,
    heading,
    timing,
    error,
)


QDRANT_URL = "http://localhost:6333"
TOP_K = 3


def build_prompt(question: str, retrieved_chunks: list) -> str:
    """Build a prompt using the retrieved policy chunks."""

    context = "\n\n".join(
        point.payload["text"]
        for point in retrieved_chunks
    )

    prompt = f"""
You are an HR policy assistant. Answer questions using only
the policy context provided below.

Instructions:
- Answer the exact question directly.
- Treat "per leave year" as the annual entitlement.
- Treat "annual entitlement" and "entitlement per leave year"
  as equivalent when the policy states a number of days per
  leave year.
- Do not introduce distinctions that the policy does not make.
- Include the applicable employee eligibility conditions.
- Never contradict information stated in the context.
- If the answer is not present in the context, say so clearly.

Policy context:
{context}

Question:
{question}

Answer in one or two sentences. Give the answer directly:
"""

    return prompt.strip()


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
            "[1/4] Generating question embedding using Ollama..."
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
            print(f"\n[Chunk {i}]")
            print(f"Section: {point.payload.get('section_title')}")
            print(point.payload["text"])

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
            "(gemma3:4b)..."
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
