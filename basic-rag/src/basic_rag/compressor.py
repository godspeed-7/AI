"""Shrink retrieved context before it reaches the LLM (experiments only).

In:  the question + the retrieved context as one string.
Out: a shorter context string, using one of three strategies:
       none         return the context unchanged (the baseline)
       extractive   keep the keep_sentences sentences most similar to
                    the question, in their original order
       abstractive  ask the LLM to rewrite the context, keeping only
                    what is relevant to the question

Caveats:
- Extractive returns the context unchanged when it has keep_sentences
  sentences or fewer, which is common with short chunks and TOP_K = 3.
- Extractive mixes sentences from all chunks, so a kept sentence can
  lose the [document | section] label that came before it.
- Abstractive adds an LLM call per question and can drop or distort a
  fact; the answer then repeats the mistake.
"""

import math
import re

from basic_rag.config import EMBED_DOCUMENT_PREFIX
from basic_rag.embedder import generate_embedding
from basic_rag.generator import generate_answer


def compress_context(
    question: str,
    context: str,
    strategy: str = "extractive",
    keep_sentences: int = 6,
) -> str:
    """Compress retrieved context using the selected strategy.

    Raises ValueError for an unknown strategy.
    """

    if strategy == "none":
        return context

    if strategy == "extractive":
        return _extractive_compress(
            question=question,
            context=context,
            keep_sentences=keep_sentences,
        )

    if strategy == "abstractive":
        return _abstractive_compress(question, context)

    raise ValueError(
        f"Unknown compression strategy: {strategy}. "
        "Choose 'none', 'extractive', or 'abstractive'."
    )


def _split_sentences(context: str) -> list[str]:
    """Split context into sentences while preserving their text."""
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", context.strip())
        if sentence.strip()
    ]


def _cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """Calculate cosine similarity between two embedding vectors."""
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))

    magnitude_a = math.sqrt(sum(value * value for value in vector_a))
    magnitude_b = math.sqrt(sum(value * value for value in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def _extractive_compress(
    question: str,
    context: str,
    keep_sentences: int,
) -> str:
    """Select the sentences most relevant to the question."""
    sentences = _split_sentences(context)

    if not sentences or keep_sentences <= 0:
        return ""

    if len(sentences) <= keep_sentences:
        return context

    # The question gets the default (query) prefix; sentences are
    # document text, so they get the document prefix, as at ingestion.
    question_embedding = generate_embedding(question)
    scored_sentences = []

    for index, sentence in enumerate(sentences):
        sentence_embedding = generate_embedding(
            sentence, prefix=EMBED_DOCUMENT_PREFIX
        )

        score = _cosine_similarity(
            question_embedding,
            sentence_embedding,
        )

        scored_sentences.append((index, sentence, score))

    # Select the highest-scoring sentences.
    selected = sorted(
        scored_sentences,
        key=lambda item: item[2],
        reverse=True,
    )[:keep_sentences]

    # Restore the original document order.
    selected.sort(key=lambda item: item[0])

    return " ".join(sentence for _, sentence, _ in selected)


def _abstractive_compress(question: str, context: str) -> str:
    """Ask the LLM to condense context while preserving relevant facts.

    Uses generator.generate_answer, so it runs with LLM_MODEL at
    TEMPERATURE 0 and gives the same compression on every run.
    """
    prompt = f"""
You are compressing retrieved context for a question-answering system.

Question:
{question}

Retrieved context:
{context}

Instructions:
- Keep only information relevant to answering the question.
- Preserve all relevant numbers, dates, limits, conditions, and exceptions.
- Do not invent facts or use information outside the supplied context.
- Do not change the meaning of any policy.
- If a relevant condition or exception is necessary to interpret a rule,
  retain it.
- Return only the compressed context, not an answer to the question.
- If the context does not contain relevant information, say so.
"""

    return generate_answer(prompt)
