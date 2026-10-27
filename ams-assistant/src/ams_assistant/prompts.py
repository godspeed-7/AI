"""Query step 2: the prompt the LLM answers from.

In:  the question + the Documents the vector store returned.
Out: PROMPT.invoke({"context": ..., "question": ...}) -> two chat
     messages: a system message with the answering rules, and a human
     message with the labelled chunks and the question.

Strategy: RULES are copied word for word from basic-rag's prompts.py,
so the first comparison between the two projects tests retrieval, not
wording. From then on each project tunes its own prompt.

Caveats:
- Chunks are labelled with their file name only ([leave_policy_india.txt]);
  they have no document title or section metadata, unlike basic-rag's.
- basic-rag sends one string ending in "Answer:"; here the rules are a
  system message and the model replies in its own turn, so "Answer:"
  is dropped.
- Don't use evaluation questions (or their answers) as examples in the
  rules; that shows the model the test answers and inflates the score.
"""

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate


RULES = """You are an assistant for AMS employees. Answer the user's question
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
context genuinely lacks the answer."""


# {context} and {question} are filled on every call. Literal braces in
# the text would need doubling ({{ }}); the rules have none.
PROMPT = ChatPromptTemplate.from_messages([
    ("system", RULES),
    ("human", "Policy context:\n{context}\n\nQuestion:\n{question}"),
])


def format_docs(docs: list[Document]) -> str:
    """Join the chunks' texts, each under a [file name] label, separated
    by blank lines, so the model can tell which document each came from.
    """
    return "\n\n".join(
        f"[{doc.metadata['source']}]\n{doc.page_content}" for doc in docs
    )
