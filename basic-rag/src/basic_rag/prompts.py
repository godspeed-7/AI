"""Query step 3: build the prompt the LLM answers from.

In:  the question + the chunks returned by vector_store.search().
Out: one prompt string: the answering rules, then each chunk under a
     [document title | section] label, then the question.

Caveats:
- query.py and evals/evaluate_answers.py share build_prompt, so the
  eval always tests the real prompt. Experiments that change the
  context text (e.g. compression) use format_context and
  build_prompt_from_context, so they get the same labels and rules.
- Don't use evaluation questions (or their answers) as examples in the
  rules; that shows the model the test answers and inflates the score.
"""


def build_prompt(question: str, retrieved_chunks: list) -> str:
    """Build a focused prompt using the retrieved policy chunks.

    `retrieved_chunks` are Qdrant points from vector_store.search.
    Same as build_prompt_from_context(question,
    format_context(retrieved_chunks)).
    """
    return build_prompt_from_context(
        question, format_context(retrieved_chunks)
    )


def format_context(retrieved_chunks: list) -> str:
    """Join the chunks' texts, each under a label naming its document
    and section, e.g.
        [EMPLOYEE LEAVE POLICY (INDIA), Version 2.1 | 4.1 Standard ...]
    so the model can tell apart similar rules from different documents
    or versions. Chunks are separated by blank lines; points without
    text are skipped.
    """
    return "\n\n".join(
        f"[{point.payload.get('document_title', '')} | "
        f"{point.payload.get('section', '')}]\n"
        f"{point.payload['text']}"
        for point in retrieved_chunks
        if point.payload and point.payload.get("text")
    )


def build_prompt_from_context(question: str, context: str) -> str:
    """Build the prompt from an already formatted context string: the
    answering rules, then the context, then the question."""

    prompt = f"""
You are an assistant for AMS employees. Answer the user's question
using only the company policy context provided below.

Follow these rules in order:

1. Identify the exact policy topic and leave category in the question.
   Do not confuse annual leave, casual leave, sick leave, or parental leave.

2. Find the statement in the context that directly answers the question.
   Use that statement as the primary evidence for your answer.

3. If the context explicitly states a number of days per leave year
   for the leave type asked about, treat that as the entitlement for
   that leave year.

4. Do not say that an entitlement is unspecified, missing, or cannot
   be determined when the context explicitly states the answer.
   Do not introduce distinctions that the policy does not make.

5. Apply policy rules to the user's specific scenario. If the question
   includes the user's own numbers, dates, or circumstances, compare
   them with the relevant limits or conditions in the context and state
   the outcome, while preserving any relevant conditions or exceptions.

6. Preserve relevant eligibility conditions, exceptions, deadlines,
   approval requirements, and limits. Do not invent conditions or
   exceptions that are not in the context.

7. Only answer if the context directly addresses the question. If it
   only covers something related, say that you cannot determine the
   answer from the available policy context. Never claim that the
   policy does not cover something; only that the provided context
   does not.

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
