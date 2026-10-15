# Basic RAG: HR Leave Policy

A small Retrieval-Augmented Generation (RAG) project built from scratch in Python. It uses Ollama to create embeddings and generate answers, and Qdrant to store and retrieve document chunks. The project intentionally avoids LangChain so each RAG step remains visible.

## Current architecture

```text
HR policy text file
        |
        v
    Parser (load text)
        |
        v
 Chunker (29 chunks)
        |
        v
Ollama: all-minilm (384-dimensional embeddings)
        |
        v
Qdrant collection: hr_leave_policy

User question -> all-minilm embedding -> Qdrant top-3 retrieval
                                      |
                                      v
                         Prompt = question + retrieved context
                                      |
                                      v
                         Ollama: llama3.2:3b -> answer
```

## Project layout

```text
basic-rag/
├── documents/
│   ├── hr_leave_policy.txt
│   └── evaluation_questions.csv
├── src/
│   ├── __init__.py
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── vector_store.py
│   ├── generator.py
│   └── logger.py
├── ingest.py
├── query.py
├── main.py
├── pyproject.toml
└── uv.lock
```

`test_generator.py` was used as a temporary generator test during development; remove it if it is no longer needed. `main.py` may be an earlier copy of the ingestion flow; check whether it is still needed before removing it.

## Requirements

- Python project managed with [`uv`](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) serving its local HTTP API at `http://localhost:11434`
- [Qdrant](https://qdrant.tech/) reachable at `http://localhost:6333`
- Python dependencies recorded in `pyproject.toml` and `uv.lock`

Current model names:

- `all-minilm` — embeddings; returns 384-dimensional vectors
- `llama3.2:3b` — answer generation

The models must be available to the Ollama instance used by the Python app. Ollama models downloaded inside a Docker container are separate from models downloaded into native macOS Ollama.

## Start the services

### Ollama

Start the native Ollama application on macOS. Confirm its API responds:

```bash
curl http://localhost:11434/api/tags
```

Confirm the models are installed:

```bash
ollama list
```

If needed, download them:

```bash
ollama pull all-minilm
ollama pull llama3.2:3b
```

### Qdrant

Qdrant must be running and reachable at `http://localhost:6333`. In the development setup it runs in Docker. If the container already exists, check it with:

```bash
docker ps
```

If it is stopped, start the existing container with:

```bash
docker start qdrant
```

## Install project dependencies

From the project directory:

```bash
uv sync
```

Add new dependencies with `uv add <package>`. The project uses Colorama for colored console logs.

## Ingest the document

Run this whenever the source policy changes or you need to rebuild its vectors:

```bash
uv run python ingest.py
```

The ingestion process:

1. Loads `documents/hr_leave_policy.txt`.
2. Splits the text into chunks (the current run creates 29).
3. Generates an embedding for each chunk through Ollama's `/api/embed` endpoint.
4. Connects to Qdrant and upserts chunks into the `hr_leave_policy` collection.
5. Prints progress messages and elapsed times using the shared logger.

The current embedding dimension is 384, matching the Qdrant collection configuration. If you change embedding models, regenerate all document embeddings and question embeddings using the same model. Matching dimensions alone do not mean vectors from different models are compatible.

## Ask a question

Run:

```bash
uv run python query.py
```

Enter a question about the HR leave policy. The query flow:

1. Embeds the question using `all-minilm`.
2. Retrieves the three nearest chunks from Qdrant using cosine similarity.
3. Builds a prompt containing the retrieved context and question.
4. Sends the prompt to `llama3.2:3b` through Ollama's `/api/generate` endpoint.
5. Prints the answer and timings for each stage.

The prompt instructs the model to use only the provided context and to say when the answer cannot be found in that context. This is a prompt instruction, not a guarantee that the model will always follow it.

## Shared colored logging

`src/logger.py` defines reusable helpers such as `heading`, `progress`, `info`, `success`, `error`, and `timing`. Both `ingest.py` and `query.py` use these helpers for consistent terminal output.

The current query logs measure embedding generation, Qdrant retrieval, prompt construction, and LLM generation separately. Total time may also include time spent entering the question if the timer starts before `input()`.

## Environment and configuration

Current local endpoints are defined in the source files:

- Ollama embeddings: `http://localhost:11434/api/embed`
- Ollama generation: `http://localhost:11434/api/generate`
- Qdrant: `http://localhost:6333`

For a larger application, consider moving endpoints, model names, collection name, and chunking parameters into configuration or environment variables rather than duplicating literals.

## Known limitations and next steps

- **Evaluate retrieval quality.** Use `documents/evaluation_questions.csv` to test direct, multi-hop, exception, and unanswerable questions. Compare answers against expected behavior rather than relying on one successful query.
- **Inspect retrieved chunks.** Print the section, chunk index, and similarity score so retrieval errors are visible.
- **Measure answer quality and latency.** Record generation time and whether each answer is correct and grounded in the retrieved context.
- **Consider streaming generation.** The current generator uses `stream: false`, so the answer appears only after generation finishes. Streaming can show partial output while the model works.
- **Consider batch embeddings.** The current embedding function makes one request per chunk; Ollama's embedding API can accept multiple inputs in one request.
- **Improve error handling.** Add clear messages for unavailable Ollama/Qdrant services and HTTP failures.
- **Check stale points if chunk count changes.** Upserting IDs 0–28 replaces those points, but does not automatically remove old points with IDs beyond the new chunk count. Recreate/clear the collection or explicitly delete stale points when rebuilding with a different number of chunks.
- **Keep the embedding model consistent.** If changing from `all-minilm`, regenerate the document vectors and use the same new model for queries.

## Current milestone

The end-to-end pipeline is working: document ingestion creates 29 embeddings and stores them in Qdrant; query-time embedding, top-3 retrieval, prompt construction, and Ollama answer generation all run. Colored progress logs and per-stage timing are in place. Native Ollama has been started on an Apple M4 Mac to test Metal acceleration, while Qdrant remains in Docker.
