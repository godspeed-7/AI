"""Experiment: does splitting multi-part questions into sub-questions
improve retrieval?

In:  the answerable questions in ams-data/evaluation_questions.csv.
Out: Hit Rate, Recall and MRR @TOP_K for two pipelines, side by side:
         Baseline    PRODUCTION (pipeline.py)
         Decomposed  PRODUCTION with decompose on (decomposer.py)
     plus every question that flipped, with its sub-questions.

Strategy: compare() (evaluation.py) runs both pipelines with the same
steps and scoring. Each sub-question is searched and reranked on its
own, then the parts' results are merged by taking turns into TOP_K,
so the scores stay comparable. Recall is the number to watch: the
technique targets questions whose search found only one of the
sections they need.

Usage (from ams-assistant/):
    uv run python experiments/evaluate_query_decomposition.py

Caveats:
- One LLM call per question the first time (cached after), 4 at a time.
- New sub-questions mean new reranker pairs: the first run reranks
  them, later runs read the saved scores.
- Run ingest.py first; needs Ollama and Qdrant running.
"""

from dataclasses import replace

from ams_assistant.evaluation import compare
from ams_assistant.pipeline import PRODUCTION


def main():
    """Score both pipelines and print the comparison."""
    compare(PRODUCTION, {"Decomposed": replace(PRODUCTION, decompose=True)})


if __name__ == "__main__":
    main()
