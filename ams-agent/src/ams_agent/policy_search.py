"""Handbook search as a tool: the tuned RAG pipeline (walk 7).

In:  a search text the model writes, e.g. "annual leave carry-over
     India".
Out: search_policies -> the TOP_K best handbook sections, each under
     its [file] label, with its handbook, chapter and section number;
     warm_up(), called once at startup (app.py, run_evals.py).

Strategy: search is a tool (load late): handbook text enters the
context only when a question needs it. Under it runs the RAG pipeline
we built and tuned in ams-assistant (vector search in Qdrant, then the
bge reranker: 97.34% of questions find their section in the top 3),
used as a library, not copied, so there is one source. The model
decides whether and what to search, and writes the answer itself.

Caveats:
- Needs Qdrant running with the ingested collection (ams-assistant's
  ingest.py, re-run whenever a handbook changes) and Ollama's
  embedding model; the reranker (~2 GB) loads in warm_up(). A search
  over SEARCH_TIMEOUT is given up on (walk 11); Qdrant's and Ollama's
  own time limits are the pipeline's (ams-assistant, not changed). On a
  laptop CPU a new search takes up to ~10 s (a repeat is cached).
- The search text is written by the model, not a person; the 97.34%
  was measured on people's questions.
"""

from concurrent.futures import ThreadPoolExecutor

from ams_assistant.pipeline import PRODUCTION, retrieve
from ams_assistant.prompts import format_docs
from langchain.tools import tool

from ams_agent.config import SEARCH_TIMEOUT

MAX_QUERY_CHARS = 300  # a search text, not a document
# Searches run here, so one that hangs can be given up on (walk 11).
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
    query = query.strip()[:MAX_QUERY_CHARS]
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
