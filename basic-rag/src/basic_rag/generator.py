
import json
from urllib.request import Request, urlopen

from basic_rag.config import LLM_MODEL, OLLAMA_GENERATE_URL, TEMPERATURE


def generate_answer(prompt: str) -> str:
    """Generate an answer using the configured Ollama model."""

    # Prepare the request body
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

    # Send the request to Ollama
    with urlopen(request, timeout=180) as response:
        response_data = json.loads(
            response.read().decode("utf-8")
        )

    # Return the generated text
    return response_data["response"].strip()
