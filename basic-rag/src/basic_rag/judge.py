"""LLM judge: grade one generated answer (used by evals and experiments).

In:  the question, the reference answer, the context the answerer was
     given, and the generated answer.
Out: a dict with correctness, context_support, and completeness (each
     0-2), total_score (0-6), and the judge's explanation.

Shared by evals/evaluate_answers.py and
experiments/evaluate_context_compression.py, so both grade with the same
prompt and their scores can be compared.

Caveats:
- The judge is the same small model as the answerer (gemma3:4b), so
  treat small score differences as noise.
- Raises ValueError if the judge's reply isn't valid JSON with valid
  scores.
"""

import json
import re
from urllib.request import Request, urlopen

from basic_rag.config import JUDGE_MODEL, OLLAMA_GENERATE_URL


def judge_answer(
    question: str,
    expected_answer: str,
    generated_answer: str,
    retrieved_context: str,
) -> dict:
    """Evaluate the generated answer against the reference and context.

    Returns a dict with correctness, context_support, and completeness
    (each 0-2), total_score (0-6), and the judge's explanation. Raises
    ValueError if the judge's reply isn't valid JSON with valid scores.
    """

    # The judge sees the question, the reference answer, the chunks the
    # answerer was given, and the generated answer.
    judge_prompt = f"""
You are evaluating the quality of an answer produced by a RAG system
for AMS company policies.

Evaluate the generated answer using the question, reference answer,
and retrieved policy context.

Scoring rules:

- correctness: Is the generated answer factually consistent with the
  reference answer? Score 0, 1, or 2.
- context_support: Are the claims in the generated answer supported by
  the retrieved context? Score 0, 1, or 2.
- completeness: Does the generated answer include the important details
  needed to answer the question, compared with the reference answer?
  Score 0, 1, or 2.

For all scores:
0 = Poor or incorrect
1 = Partially correct, supported, or complete
2 = Good, correct, supported, or complete

Important rules:

- Different wording is acceptable if the meaning is equivalent.
- Do not reward an answer for repeating the reference if the context
  contradicts or fails to support it.
- If the context does not contain enough information, an answer that
  appropriately says so can be correct.
- Do not assume facts that are absent from the context.
- Judge the answer against the actual question, not just keyword overlap.
- Do not penalize a concise answer when it contains all the details
  necessary to answer the question.
- If an answer contradicts itself, consider that in the correctness
  and completeness scores.
- Explain the scores briefly and objectively.

Return only valid JSON in this exact structure:
{{
  "correctness": 0,
  "context_support": 0,
  "completeness": 0,
  "explanation": "Brief explanation of the scores"
}}

Question:
{question}

Reference answer:
{expected_answer}

Retrieved policy context:
{retrieved_context}

Generated answer:
{generated_answer}
"""

    # format="json" asks Ollama for valid JSON so the scores can be
    # parsed; temperature 0 keeps grading repeatable.
    request_data = {
        "model": JUDGE_MODEL,
        "prompt": judge_prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    request = Request(
        url=OLLAMA_GENERATE_URL,
        data=json.dumps(request_data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=180) as response:
        response_data = json.loads(response.read().decode("utf-8"))

    judge_text = response_data["response"].strip()

    try:
        result = json.loads(judge_text)
    except json.JSONDecodeError:
        # Fallback if the model wraps JSON in additional text.
        match = re.search(r"\{.*\}", judge_text, re.DOTALL)
        if not match:
            raise ValueError(
                f"Judge did not return valid JSON: {judge_text}"
            )
        result = json.loads(match.group())

    score_fields = ("correctness", "context_support", "completeness")

    # Reject anything that isn't exactly 0, 1, or 2. bool is checked
    # first because in Python True/False count as ints (1/0).
    for field in score_fields:
        score = result.get(field)
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or score not in (0, 1, 2)
        ):
            raise ValueError(
                f"Invalid judge score for '{field}': {score!r}"
            )

    result["explanation"] = str(result.get("explanation", "")).strip()
    result["total_score"] = sum(result[field] for field in score_fields)

    return result
