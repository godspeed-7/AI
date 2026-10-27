"""Query pipeline (LangChain version): ask a question, get an answer.

Steps:
    1. Retrieve   embed the question and find the TOP_K closest chunks
                  (similarity_search_with_score)
    2. Prompt     fill PROMPT with the labelled chunks and the question
                  (prompts.py)
    3. Generate   send the prompt messages to LLM_MODEL (ChatOllama)
    4. Chain      (next)

The retrieved chunks are printed with their scores before the answer,
so you can see what the model was given. Only reads from Qdrant.

Caveats:
- Run ingest.py first; needs Ollama (with both models pulled) and
  Qdrant running.
- The question is embedded without nomic's "search_query: " prefix.
"""

from langchain_ollama import ChatOllama

from ams_assistant.config import LLM_MODEL, TEMPERATURE, TOP_K
from ams_assistant.prompts import PROMPT, format_docs
from ams_assistant.vector_store import get_vector_store


def main():
    """Read a question, run steps 1-3, and print chunks and answer."""
    question = input("Enter your question: ").strip()

    if not question:
        print("Please enter a question.")
        return

    # Step 1: Retrieve. Embeds the question (embed_query) and runs the
    # cosine search in one call; each result is a (Document, score) pair.
    vector_store = get_vector_store()
    results = vector_store.similarity_search_with_score(question, k=TOP_K)

    # "Closest", not "relevant": search always returns TOP_K chunks, even
    # for an off-topic question. A low score is the warning.
    print(f"\nTop {len(results)} chunks:")

    for rank, (doc, score) in enumerate(results, start=1):
        print(f"\n[{rank}] score {score:.4f} | {doc.metadata['source']}")
        print(doc.page_content[:300])

    # Step 2: Prompt. Fill the template's {context} and {question}; the
    # result is a list of chat messages (system + human).
    docs = [doc for doc, _score in results]
    prompt_value = PROMPT.invoke({
        "context": format_docs(docs),
        "question": question,
    })

    # Step 3: Generate. ChatOllama sends the messages to Ollama's
    # /api/chat and returns an AIMessage (the answer + token counts).
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)
    answer = llm.invoke(prompt_value)

    print(f"\nAnswer ({LLM_MODEL}):")
    print(answer.content)

    usage = answer.usage_metadata
    print(
        f"\nTokens: {usage['input_tokens']} in, "
        f"{usage['output_tokens']} out"
    )


if __name__ == "__main__":
    main()
