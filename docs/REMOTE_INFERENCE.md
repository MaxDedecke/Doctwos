# Remote inference endpoint

Doctus can use a managed remote service for chat and embeddings. The service is
contacted by the backend and parser containers, never directly by the browser.
Keep keys in the deployment `.env`; do not enter the embedding key in a browser
profile.

## Configuration

Use the remote overlay instead of the local Ollama service:

```bash
docker compose -f docker-compose.yml -f docker-compose.remote-inference.yml up -d
```

Set these values in `.env` before starting it:

```dotenv
# Native Ollama chat service
OLLAMA_BASE_URL=https://inference.example:11434
OLLAMA_API_KEY=replace-with-chat-key
LLM_MODEL=qwen2.5-coder:14b

# Separate embedding service
EMBEDDING_BASE_URL=https://inference.example/v1
EMBEDDING_API_KEY=replace-with-embedding-key
EMBEDDING_PROVIDER=openai
EMBEDDING_AUTO_PULL=false
```

`EMBEDDING_PROVIDER=ollama` uses native Ollama endpoints
`/api/embeddings` and `/api/embed`. `EMBEDDING_PROVIDER=openai` uses the
OpenAI-compatible endpoint `/embeddings` with the request body
`{"model": "…", "input": "…"}`. The base URL must include a path segment
such as `/v1` if the provider requires it.

The parser sends an `Authorization: Bearer …` header whenever a key is set.
For managed endpoints set `EMBEDDING_AUTO_PULL=false`; Doctus then never calls
Ollama's privileged `/api/pull` endpoint.

## Chat endpoint variants

The environment variables above configure a native Ollama chat endpoint
(`/v1/chat/completions` or `/api/chat` for compliance checks). If the Qwen
service instead offers an OpenAI-compatible API, create an **OpenAI** profile in
Settings → AI with the provider URL, model name and key. That profile is used
for interactive chat and agent calls.

## Before first indexing

The embedding model must return exactly 1024 dimensions, matching Doctus'
pgvector column. Reindex sources after changing an embedding model or service;
mixing vectors from different models in one index is intentionally prevented.

Confirm with the service owner which exact chat and embedding paths they expose,
the model IDs, and whether their key uses a Bearer header. If their API differs
from native Ollama or OpenAI-compatible embeddings, add a small provider adapter
instead of guessing the path or response format.
