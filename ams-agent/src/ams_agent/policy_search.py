"""Handbook search as a tool, on ams-assistant's tuned RAG pipeline.

In:  a search text the model writes ("annual leave carry-over India").
Out: search_policies -> the TOP_K best sections, each with its handbook
     and section number; warm_up() at startup.

How: Qdrant vector search + bge reranker (97.34% top-3), imported from
ams-assistant, not copied.

Watch out: needs Qdrant and Ollama running; a new search takes ~10 s.
"""

from concurrent.futures import ThreadPoolExecutor

from ams_assistant.pipeline import PRODUCTION, retrieve
from ams_assistant.prompts import format_docs
from langchain.tools import tool

from ams_agent.config import SEARCH_QUERY_CHARS, SEARCH_TIMEOUT

# Searches run here, so one that hangs can be given up on.
SEARCHES = ThreadPoolExecutor(max_workers=2, thread_name_prefix="search")


@tool(parse_docstring=True)
def search_policies(query: str) -> str:
    """Search the AMS handbooks for company rules and policies.

    Use it for any question about a rule: leave (entitlements,
    carry-over, probation limits, holidays), joining, probation, notice
    and leaving, pay and bonus, travel and expenses (hotel limits,
    allowances, late claims, receipts), corporate cards, laptops,
    phones and IT access, security, offices, ODCs and facilities,
    learning and trainings, legal and compliance. Rules can differ
    between India and the US: say which. Returns the 3 most relevant
    handbook sections, each with its handbook and section number.

    Args:
        query: What to look for, in plain words, e.g. "annual leave
            carry-over India" or "hotel limit per night US".
    """
    query = query.strip()[:SEARCH_QUERY_CHARS]
    if not query:
        return "Give a search text, e.g. 'annual leave carry-over India'."
    search = SEARCHES.submit(retrieve, [query], PRODUCTION)
    try:
        return format_docs(search.result(timeout=SEARCH_TIMEOUT)[0])
    except TimeoutError:  # the search keeps running, but nobody waits
        return (f"The handbook search took over {SEARCH_TIMEOUT} s and was"
                " stopped. Answer from the records if you can, and say the"
                " handbook rule couldn't be checked right now.")


def warm_up() -> None:
    """One search at startup, so the reranker loads before the first
    question instead of during it (~10 s)."""
    retrieve(["annual leave"], PRODUCTION)
