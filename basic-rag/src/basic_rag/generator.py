"""Query step 4: send the finished prompt to the LLM.

In:  one prompt string (built by prompts.py).
Out: the LLM's answer text.

Calls Ollama's /api/generate with LLM_MODEL (gemma3:4b) and TEMPERATURE
0, so the same prompt gives the same answer.
"""

import json
from urllib.request import Request, urlopen

from basic_rag.config import LLM_MODEL, OLLAMA_GENERATE_URL, TEMPERATURE


def generate_answer(prompt: str) -> str:
    """Generate an answer using the configured Ollama model."""

    # Prepare the request body.
    # stream=False: wait for the whole answer instead of receiving it
    # word by word. Simpler, but nothing prints until it's finished.
    # temperature=0: the same prompt gives the same answer every time.
    request_data = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
        },
    }

    # Convert the request body to JSON bytes
    request_body = json.dumps(request_data).encode("utf-8")

    # Create the HTTP request
    request = Request(
        url=OLLAMA_GENERATE_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Send the request to Ollama. Generation is slow on a laptop, hence
    # the long timeout.
    with urlopen(request, timeout=180) as response:
        response_data = json.loads(
            response.read().decode("utf-8")
        )

    # Return the generated text
    return response_data["response"].strip()
