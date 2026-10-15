
import time

from src.embedder import generate_embedding
from src.vector_store import create_vector_store, COLLECTION_NAME
from src.generator import generate_answer
from src.logger import info, progress, success, heading, timing, error


def build_prompt(question: str, retrieved_chunks: list) -> str:
    context = "\n\n".join(
        point.payload["text"]
        for point in retrieved_chunks
    )

    prompt = f"""
You are an assistant answering questions about the HR leave policy.

Answer the question using only the provided context.
If the context does not contain the answer, say you cannot
find the answer in the provided policy context.

Context:
{context}

Question:
{question}

Answer:
"""

    return prompt.strip()


def main():
    start_time = time.perf_counter()

    heading("HR POLICY RAG SYSTEM")

    question = input("\nEnter your question: ").strip()

    if not question:
        error("Please enter a question.")
        return

    # Step 1: Generate question embedding
    progress("[1/4] Generating question embedding using Ollama...")
    step_start = time.perf_counter()

    question_embedding = generate_embedding(question)

    success("Question embedding generated")
    timing("Embedding generation", time.perf_counter() - step_start)

    # Step 2: Retrieve relevant chunks
    progress("\n[2/4] Searching Qdrant for relevant chunks...")
    step_start = time.perf_counter()

    client = create_vector_store()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=question_embedding,
        limit=3,
        with_payload=True,
    ).points

    success(f"Retrieved {len(results)} relevant chunks")
    timing("Qdrant retrieval", time.perf_counter() - step_start)

    # Step 3: Build prompt
    progress("\n[3/4] Building prompt with retrieved context...")
    step_start = time.perf_counter()

    prompt = build_prompt(question, results)

    success("Prompt prepared")
    timing("Prompt preparation", time.perf_counter() - step_start)

    # Step 4: Generate answer
    progress("\n[4/4] Generating answer using Ollama (llama3.2:3b)...")
    info("The model is generating your answer. Please wait...")

    step_start = time.perf_counter()

    answer = generate_answer(prompt)

    success("Answer generated")
    timing("LLM generation", time.perf_counter() - step_start)

    # Display answer
    heading("RAG ANSWER")
    print(answer)

    # Total time
    total_time = time.perf_counter() - start_time

    print()
    timing("Total processing time", total_time)


if __name__ == "__main__":
    main()
