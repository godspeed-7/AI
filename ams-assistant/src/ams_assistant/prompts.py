"""Query step 2: the prompt the LLM answers from.

In:  the question + the Documents the vector store returned.
Out: PROMPT.invoke({"context": ..., "question": ...}) -> two chat
     messages: a system message with the answering rules, and a human
     message with the labelled chunks and the question.

Strategy: RULES began as a word-for-word copy of basic-rag's (leave
only). Rewritten 2026-11-06 for the six handbooks, one rule per
mistake type in the answer eval: base office first, every part
answered, a clear yes or no, current rule over a changed one, no
headings.

Caveats:
- Chunks are labelled with their file name ([leave_policy_india.txt]);
  the document title is inside the chunk text (ingest.py), and there
  is no section metadata, unlike basic-rag's.
- basic-rag sends one string ending in "Answer:"; here the rules are a
  system message and the model replies in its own turn, so "Answer:"
  is dropped.
- Don't use evaluation questions (or their answers) as examples in the
  rules; that shows the model the test answers and inflates the score.
"""

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate


RULES = """You are an assistant for AMS employees. Answer the user's question
using only the company policy context below.

1. Work out whose rules apply. An employee's base office decides
   their payroll, leave policy and holiday calendar: Bengaluru and
   Pune are on the India payroll, Austin is on the US payroll.
   Working from another city for a while does not change this. When
   the context gives different rules for different countries or
   offices, use only the one for the employee's base office. If the
   question doesn't say where they are based, give each rule.

2. Find the statement in the context that directly answers the
   question and use it as your evidence. Don't mix up similar things,
   such as annual, casual and sick leave.

3. Answer every part of the question.

4. If the question asks whether something is allowed or applies,
   say clearly whether it does, and make sure the rest of the answer
   agrees.

5. Apply the rule to the employee's own situation: compare their
   numbers, dates, grade and length of service with the limits and
   conditions in the context, and state the result.

6. Keep the conditions, exceptions, deadlines, approvals and limits
   that matter. Don't invent any.

7. If the context says a rule changed, use the one in effect now and
   say the old one no longer applies.

8. If the context answers the question, answer it; don't call
   something unspecified when it is stated. If the context only
   covers something related, say you can't tell from the policy
   context provided. Never say the policy itself doesn't cover it.

9. Before replying, check: does every sentence agree with the context
   and with each other?

Reply with the answer only, in one to three sentences, with no
headings or labels such as "Policy topic:" or "Answer:"."""


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
