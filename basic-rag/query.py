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
    """Build a focused prompt using the retrieved policy chunks."""

    context = "\n\n".join(
        point.payload["text"]
        for point in retrieved_chunks
        if point.payload and point.payload.get("text")
    )

    prompt = f"""
You are an HR policy assistant. Answer the user's question using
only the policy context provided below.

Follow these rules in order:

1. Identify the exact policy topic and leave category in the question.
   Do not confuse annual leave, casual leave, sick leave, or parental leave.

2. Find the statement in the context that directly answers the question.
   Use that statement as the primary evidence for your answer.

3. If the context explicitly states a number of days per leave year,
   treat that as the entitlement for that leave year. For example,
   "6 days of casual leave per leave year" directly answers a question
   asking for the annual casual-leave entitlement.

4. Do not say that an entitlement is unspecified, missing, or cannot
   be determined when the context explicitly states the answer.
   Do not introduce distinctions that the policy does not make.

5. Apply policy rules to the user's specific scenario. For example,
   if the standard carry-over limit is 5 days and the employee has
   8 unused days, explain that all 8 days cannot be carried over
   under the standard rule. If the employee has 4 unused days and
   the limit is 5, explain that all 4 are within the numerical limit,
   while preserving any relevant conditions or exceptions in context.

6. Preserve relevant eligibility conditions, exceptions, deadlines,
   approval requirements, and limits. Do not invent conditions or
   exceptions that are not in the context.

7. If the answer genuinely is not supported by the context, say that
   you cannot determine it from the available policy context.

8. Before responding, check your draft:
   - Does it directly answer the question?
   - Does every claim agree with the context?
   - Does any sentence contradict another sentence?
   - Have you applied any relevant number or limit to the scenario?
   Remove contradictory or unnecessary statements.

Answer concisely in one to three sentences. State the supported answer
directly; do not add a preamble about missing information unless the
context genuinely lacks the answer.

Policy context:
{context}

Question:
{question}

Answer:
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
