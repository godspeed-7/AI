import json
from urllib.request import Request, urlopen


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b"


def generate_answer(prompt: str) -> str:
    # Prepare the request body
    request_data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    # Convert the request body to JSON bytes
    request_body = json.dumps(request_data).encode("utf-8")

    # Create the HTTP request
    request = Request(
        url=OLLAMA_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Send the request to Ollama
    with urlopen(request, timeout=180) as response:
        response_data = json.loads(response.read().decode("utf-8"))

    # Return the generated text
    return response_data["response"].strip()
