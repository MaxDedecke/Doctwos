# Remote inference endpoint

Doctus can use a remote on-premise service or a cloud provider for chat and
embeddings. The backend and parser containers contact these services; the
browser never receives API keys.

## Configuration

Open **Settings → AI**, add a profile and choose one of the three operating
modes:

- **Local Ollama** always addresses the Compose service at
  `http://ollama:11434`.
- **Remote On-Premise** accepts a URL (including port and optional base
  subpath), native Ollama or OpenAI-compatible chat, a chat path/model/key and
  an independently configurable embedding URL/path/model/key.
- **Cloud** offers OpenAI (Responses API), Anthropic and Gemini when
  `llm.allowCloudProviders` is enabled in `config/features.json`.

Use **Test** before activation. It checks chat and embedding discovery with
their respective URL and key. Activation is deployment-wide and is consumed
by the API, parser worker, retrieval and link reviews without a container
restart. Keys are encrypted in PostgreSQL and API responses expose only a
`*_api_key_set` flag.

The remote overlay remains available for deployments that must omit the local
Ollama container entirely:

```bash
docker compose -f docker-compose.yml -f docker-compose.remote-inference.yml up -d
```

Environment values are now bootstrap/fallback values. Configure the effective
profile in the UI after the first start:

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

## Existing installations

Migration `0018_ai_profiles` creates the immutable local profile. If the old
deployment-wide `ai_settings` row points at an external URL, it is retained as
**Remote (migriert)** and selected, including its encrypted credentials.

## Before first indexing

The embedding model must return exactly 1024 dimensions, matching Doctus'
pgvector column. Reindex sources after changing an embedding model or service;
mixing vectors from different models in one index is intentionally prevented.

Confirm with the service owner which exact chat and embedding paths they expose,
the model IDs, and whether their key uses a Bearer header. If their API differs
from native Ollama or OpenAI-compatible embeddings, add a small provider adapter
instead of guessing the path or response format.
