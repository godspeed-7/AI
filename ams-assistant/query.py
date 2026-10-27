"""Query pipeline (LangChain version): ask a question, get an answer.

Steps (all inside build_chain(), chain.py):
    1. Retrieve   embed the question and find the TOP_K closest chunks
    2. Prompt     fill PROMPT with the labelled chunks and the question
                  (prompts.py)
    3. Generate   send the prompt messages to LLM_MODEL (ChatOllama)

The retrieved chunks are printed before the answer, so you can see
what the model was given. Only reads from Qdrant.

Caveats:
- Run ingest.py first; needs Ollama (with both models pulled) and
  Qdrant running.
- Chunks are shown without similarity scores (the retriever drops
  them), so an off-topic question still shows TOP_K chunks.
"""

from ams_assistant.chain import build_chain
from ams_assistant.config import LLM_MODEL


def main():
    """Read a question, run the chain, and print chunks and answer."""
    question = input("Enter your question: ").strip()

    if not question:
        print("Please enter a question.")
        return

    # One call runs all three steps; the result is a dict with the
    # question, the retrieved Documents, and the answer.
    result = build_chain().invoke(question)

    docs = result["docs"]
    print(docs)
    print(f"\nTop {len(docs)} chunks:")

    for rank, doc in enumerate(docs, start=1):
        print(f"\n[{rank}] {doc.metadata['source']}")
        print(doc.page_content[:300])

    answer = result["answer"]
    print(f"\nAnswer ({LLM_MODEL}):")
    print(answer.content)

    usage = answer.usage_metadata
    print(
        f"\nTokens: {usage['input_tokens']} in, "
        f"{usage['output_tokens']} out"
    )


if __name__ == "__main__":
    main()
