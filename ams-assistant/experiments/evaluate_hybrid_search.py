"""Experiment: does adding keyword search (BM25) to vector search
improve retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two pipelines, side by side:
         Baseline    PRODUCTION (pipeline.py): vector search only
         Hybrid      PRODUCTION with hybrid on: vector + keyword
                     search (keyword_search.py), merged with RRF
     plus every question that flipped.

Strategy: compare() (evaluation.py) runs both pipelines with the same
steps and scoring. Hybrid changes only the CANDIDATE_K candidates the
reranker sees: it can bring in a chunk that shares the question's exact
words but ranks low by meaning (and push another one out).

Usage (from ams-assistant/):
    uv run python experiments/evaluate_hybrid_search.py

Caveats:
- No LLM calls. New candidates mean new reranker pairs: the first run
  reranks them, later runs read the saved scores.
- A quick in-memory test; see keyword_search.py for the production way.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from dataclasses import replace

from ams_assistant.evaluation import compare
from ams_assistant.pipeline import PRODUCTION


def main():
    """Score both pipelines and print the comparison."""
    compare(PRODUCTION, {"Hybrid": replace(PRODUCTION, hybrid=True)})


if __name__ == "__main__":
    main()
