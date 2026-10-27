"""Query rewriting: turn a casual question into a clearer search query
before retrieval.

In:  {"question": "can i chill at home on fridays?"}
Out: build_rewriter().invoke(...) -> one sentence, e.g. "Can I work
     from home on Fridays under the hybrid work policy?"

Strategy: REWRITE_PROMPT started as a copy of basic-rag's. With that
copy, rewriting lowered Hit Rate from 92.48% to 84.96%: its rule
"preserve the specific leave category" made gemma add "leave" to
non-leave questions. So the rules now keep the user's key terms, forbid
new topics, and leave clear questions unchanged. Only the search uses
the rewrite; the answer prompt still gets the original question.

Caveats:
- One extra LLM call per question (slower, and gemma3:4b can drift
  from the original meaning). An experiment for now; not in chain.py.
- The new rules were written after seeing which eval questions broke,
  so an improvement here may not carry over to new questions. Never
  use wording from the eval questions as an example in the rules.
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from ams_assistant.config import LLM_MODEL, TEMPERATURE


REWRITE_PROMPT = ChatPromptTemplate.from_template("""\
You rewrite questions for semantic search over AMS company policies
(leave, holidays, travel and expenses, benefits, remote work, conduct,
onboarding and exit).

Your job is to make the question self-contained and easy to match to
the relevant policy passage, while preserving exactly what the user is
asking.

Rules:
- If the question is already clear and formal, return it unchanged.
- Preserve the user's intent exactly.
- Keep the user's key terms word for word: names, places, job titles,
  form codes, numbers, and dates.
- Replace casual or slang wording with the plain terms a policy
  document would use (for example "get my money back for a cab" ->
  "reimbursement for taxi fares").
- Do not add topics, policy areas, or words the question does not
  imply. Do not add the words "leave" or "policy" unless the question
  is about them.
- Do not answer the question.
- Do not add policy facts, assume an answer, or broaden the question.
- Keep the rewritten query concise, preferably one sentence.
- Return only the rewritten query, with no explanation or quotation marks.

Original question:
{question}

Rewritten search query:
""")


def build_rewriter():
    """Return the chain: {"question"} -> rewritten query (a string)."""
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)

    # StrOutputParser turns the AIMessage into its text (.content), so
    # the result can go straight into the retriever. A plain function
    # in a chain becomes a step too; str.strip drops the trailing "\n".
    return REWRITE_PROMPT | llm | StrOutputParser() | str.strip
