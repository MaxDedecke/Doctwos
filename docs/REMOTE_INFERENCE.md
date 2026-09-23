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

## On-Premise Two-Machine Architecture (Machine A + Machine B)

In typical high-security on-premise enterprise environments, Doctus operates across two machines in the same private LAN without internet access:

- **Machine A (Doctus Host)**: Runs PostgreSQL (pgvector), Valkey, backend-api, parser-workers, and frontend. It also retains the local Ollama container and model weights as an instant offline fallback.
- **Machine B (Inference/GPU Host)**: Runs a dedicated Ollama container or high-throughput **vLLM** service with GPU acceleration (NVIDIA Container Toolkit, PagedAttention, Continuous Batching, see O-338–O-341 in `docs/TODO.md`).

### 1. Setting up Machine B (Inference Host)

1. **Network Binding**:
   By default, Ollama only listens on `127.0.0.1`. To allow Machine A to reach Ollama over the internal LAN, configure Ollama on Machine B to listen on all interfaces:
   ```bash
   # If running via systemd:
   # In /etc/systemd/system/ollama.service.d/override.conf:
   [Service]
   Environment="OLLAMA_HOST=0.0.0.0"

   # If running via Docker:
   docker run -d --gpus all \
     -v ollama:/root/.ollama \
     -p 0.0.0.0:11434:11434 \
     -e OLLAMA_HOST=0.0.0.0 \
     --name ollama \
     ollama/ollama:latest
   ```

2. **LAN Firewall Restriction (Crucial for Security)**:
   Because Ollama has no built-in authentication, restrict port 11434 so **only Machine A** can communicate with Machine B:
   ```bash
   sudo ufw allow from <IP-OF-MACHINE-A> to any port 11434 proto tcp
   ```

3. **Required Models on Machine B**:
   The pgvector database schema requires **exactly 1024 dimensions**. The required embedding model is `bge-m3`:
   ```bash
   ollama pull bge-m3
   # Optional chat model (e.g. qwen2.5-coder:14b):
   ollama pull qwen2.5-coder:14b
   ```

### 2. Pre-Flight Verification from Machine A

Before ingesting projects, verify that Machine A can communicate with Machine B and that the embedding dimensions match:

```bash
./scripts/test-remote-inference.sh http://<IP-OF-MACHINE-B>:11434
```

The script verifies:
1. HTTP connectivity to `/api/tags`
2. Presence of the `bge-m3` model
3. Live embedding generation
4. Strict 1024-dimension vector verification

### 3. Deploying Machine A & Ad-Hoc Switching

The offline delivery bundle (`dist/doctus-offline-bundle-...`) is completely self-contained and contains all Docker images including the Ollama container and model weights.

- **Primary Remote Operation**:
  Run the installer with `--remote-inference`:
  ```bash
  ./install-offline.sh --remote-inference
  ```
  This activates `docker-compose.remote-inference.yml`, placing the local Ollama container in the `local-ollama` standby profile so it consumes 0 CPU/RAM on Machine A.

- **Ad-Hoc Switch to Local Operation**:
  If Machine B or the LAN connection becomes unavailable, switch to local operation instantly without re-downloading or re-shipping anything:
  ```bash
  # 1. Bring up the local Ollama container from standby:
  docker compose --profile local-ollama up -d ollama

  # 2. In Doctus UI (Settings → AI):
  #    Click "Aktivieren" on the pre-configured "Lokales Ollama" profile.
  ```

- **Air-Gapped Guarantee (Zero External Network Calls)**:
  - **Fonts**: All UI typography (Archivo, Space Grotesk, IBM Plex Mono) is bundled statically inside the frontend image. No requests to Google Fonts or CDNs are made.
  - **Code Viewer**: Monaco Editor is pre-packaged locally (`/monaco/vs/`); it never requests CDN scripts.
  - **Model Pulling**: `EMBEDDING_AUTO_PULL=false` by default; Doctus never attempts to pull models over the internet.

