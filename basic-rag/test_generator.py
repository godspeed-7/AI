from src.generator import generate_answer


prompt = """
Answer the following question in one sentence.

Question: What is RAG in AI?

Answer:
"""

answer = generate_answer(prompt)

print("\nGenerated answer:")
print(answer)
