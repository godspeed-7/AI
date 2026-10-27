"""Query expansion: search with the question plus a few LLM-written
alternative phrasings, and merge the results.

In:  {"question": "is food free at the bangalore office"}
Out: build_expander().invoke(...) -> NUM_ALTERNATIVES alternatives,
     e.g. ["Are meals provided at the Bangalore office?", ...];
     merge_results([docs per query, ...]) -> the TOP_K best chunks.

Strategy: unlike rewriting, the original question is always searched
too, so a bad alternative can only add weak candidates, not remove the
original's results. Merging keeps each chunk once, at its best rank;
ties go to the earlier query (the original comes first). Same merge as
basic-rag's experiments/evaluate_query_expansion.py.

Caveats:
- One extra LLM call and NUM_ALTERNATIVES extra searches per question.
  An experiment for now; not in chain.py.
- The prompt uses the same lessons as rewriter.py (keep key terms, no
  new topics), so it is not a copy of basic-rag's.
"""

import re

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from ams_assistant.config import (
    LLM_MODEL,
    NUM_ALTERNATIVES,
    TEMPERATURE,
    TOP_K,
)


EXPAND_PROMPT = ChatPromptTemplate.from_template("""\
You generate alternative search queries for semantic search over AMS
company policies (leave, holidays, travel and expenses, benefits,
remote work, conduct, onboarding and exit).

Write exactly {count} alternative ways to search for the information
requested in the user's question.

Rules:
- Preserve the user's intent exactly.
- Keep the user's key terms word for word: names, places, job titles,
  form codes, numbers, and dates.
- Use different but relevant wording, such as the plain terms a policy
  document would use instead of casual or slang wording.
- Do not add topics, policy areas, or words the question does not
  imply.
- Do not answer the question or invent policy facts.
- Do not simply repeat the original question.
- Keep each query concise, one sentence.
- Return only the queries, one per line, with no numbering, bullets,
  explanation, or quotation marks.

Original question:
{question}
""").partial(count=str(NUM_ALTERNATIVES))


def parse_queries(text: str) -> list[str]:
    """Split the LLM's reply into at most NUM_ALTERNATIVES queries,
    removing any numbering ("1.", "-") and duplicates it added anyway."""
    queries = []

    for line in text.splitlines():
        query = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line)
        query = query.strip().strip('"').strip()

        if query and query not in queries:
            queries.append(query)

    return queries[:NUM_ALTERNATIVES]


def build_expander():
    """Return the chain: {"question"} -> list of alternative queries."""
    llm = ChatOllama(model=LLM_MODEL, temperature=TEMPERATURE)
    return EXPAND_PROMPT | llm | StrOutputParser() | parse_queries


def merge_results(
    results: list[list[Document]], k: int = TOP_K
) -> list[Document]:
    """Merge several ranked result lists into the k best unique chunks.

    Walks rank 1 of every list, then rank 2, and so on, so a chunk
    lands at its best rank and ties go to the earlier list. A chunk
    found twice is kept once (Qdrant's point id identifies it).
    """
    merged = []
    seen = set()

    for rank in range(max(len(docs) for docs in results)):
        for docs in results:
            if rank < len(docs) and docs[rank].metadata["_id"] not in seen:
                seen.add(docs[rank].metadata["_id"])
                merged.append(docs[rank])

    return merged[:k]
