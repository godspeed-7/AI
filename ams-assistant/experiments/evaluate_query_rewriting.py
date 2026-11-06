"""Experiment: does rewriting the question with an LLM improve
retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two pipelines, side by side:
         Baseline    PRODUCTION (pipeline.py)
         Rewritten   PRODUCTION with rewrite on (rewriter.py)
     plus every question that flipped (miss -> hit, or hit -> miss)
     with its rewrite, so you can see why a score moved.

Strategy: compare() (evaluation.py) runs both pipelines with the same
steps and scoring; only the search text differs. Each run reranks with
its own text (the original or the rewrite).

Usage (from ams-assistant/):
    uv run python experiments/evaluate_query_rewriting.py

Caveats:
- One LLM call per question; runs 4 at a time with .batch().
- Rewrites run in parallel, so a rerun can give slightly different
  wording for a few questions.
- Reranking adds about 7 minutes (two reranked runs).
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from dataclasses import replace

from ams_assistant.evaluation import compare
from ams_assistant.pipeline import PRODUCTION


def main():
    """Score both pipelines and print the comparison."""
    compare(PRODUCTION, {"Rewritten": replace(PRODUCTION, rewrite=True)})


if __name__ == "__main__":
    main()
