"""Policy tools: what the agent can look up in the AMS handbooks.

In:  a search text the model writes, e.g.
     search_policies(query="annual leave carry-over").
Out: the top TOP_K handbook chunks, each under its [source] label.

Strategy: our RAG search as a tool. retrieve() (pipeline.py) runs the
same PRODUCTION steps as the RAG chain and the evals: vector search,
the bge reranker, glossary lines. The model decides whether and what
to search, reads the chunks, and writes the answer itself.

Caveats:
- Needs Qdrant running (the ingested collection) and Ollama's
  embedding model; the reranker loads on the first search (a few
  seconds, ~2 GB of memory).
- The search text is written by the model, not by a person; the 97.4%
  hit rate was measured on people's questions.
"""

from langchain.tools import tool

from ams_assistant.pipeline import PRODUCTION, retrieve
from ams_assistant.prompts import format_docs


@tool(parse_docstring=True)
def search_policies(query: str) -> str:
    """Search the AMS handbooks for company rules and policies.

    Use it for any question about rules: leave (entitlements,
    carry-over, probation limits, holidays), joining, probation and
    leaving, travel and expenses (hotel limits, allowances, late claims,
    receipts), corporate cards, IT and security, offices and
    facilities, learning, and legal and compliance. Returns the 3 most
    relevant handbook sections, each under its [source] label.

    Args:
        query: What to look for, in plain words, e.g. "annual leave
            carry-over" or "hotel limit per night in the US".
    """
    docs = retrieve([query], PRODUCTION)[0]
    return format_docs(docs)
