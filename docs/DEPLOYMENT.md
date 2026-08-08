# Deployment

Doctus is single-tenant, self-hosted: one instance per customer, on their own infrastructure. There are two install paths depending on whether the customer's machine has internet/registry access.

## Verified fresh-host run (develop, 2026-07-16)

This section records the actual out-of-the-box run so the same traps are not rediscovered during delivery.

| Item | Result |
|---|---|
| Source | `develop` at `d1c8f0c` before the fixes documented here |
| Host | Ubuntu 24.04.4 LTS, 4 vCPU, 7.7 GiB RAM, no swap, no GPU |
| Initial OOTB score | **4/10**: clone and secret bootstrap worked, but the one-command install and demo seed both stopped on current-code regressions |
| Score after these fixes | **8/10**, assuming Docker/Compose and an IdP already exist; TLS/real IdP setup and optional demo seeding remain operator tasks |
| Final state | All 7 Compose services healthy with zero restarts; `/health` reported DB/Valkey/Ollama `ok`; full test-Keycloak login succeeded; 3 demo projects, 24/24 `bge-m3` embeddings, 31 IFC entities and 31 entity-document links |

Observed lessons:

- A plain Ubuntu host did not have Docker or Compose. `install.sh` validates these prerequisites but intentionally does not install system packages.
- `.env` creation and generation of `MASTER_ENCRYPTION_KEY`/`SESSION_SECRET_KEY` worked unattended.
- Docker 29 failed the original parallel `docker compose build`: `parser-worker` and `parser-beat` share `doctus-parser-worker:<tag>`, so their simultaneous exports raced with `image ... already exists`. The installer and offline builder now build the three distinct images serially (`backend-api`, `parser-worker`, `frontend`).
- Ubuntu's Compose package printed `Docker Compose is configured to build using Bake, but buildx isn't installed`. This warning was harmless; all serial builds completed without Buildx.
- The old demo instructions had drifted behind the schema (`Repository` was migrated to `KnowledgeSource(type="Git")`), referenced a removed `IFC_FILE` constant, and omitted the Lindenhof fixture file. The scripts and fixture are now aligned with the current schema; keep the verification query in the demo section below.
- On this 8GB CPU-only host, Mistral NeMo 12B is not a viable default. The pilot now uses `LLM_MODEL=disabled`: only `bge-m3` is installed, so ingestion/search embeddings work while local chat and LLM-based compliance intentionally return a configuration error. Do not enable a local LLM here.
- The frontend polls `/chat/typing-statement` for a decorative start-screen question even when nobody chats. In embedding-only mode the endpoint now returns its static fallback immediately, avoiding hidden background LLM attempts and recurring log warnings.
- Measured idle memory for the 7-service Compose stack was about **671 MiB** after seeding, with `bge-m3` installed but unloaded. The disposable Keycloak used another ~529 MiB and is not part of the Doctus Compose stack.

## Prerequisites (both paths)

- Docker Engine + the Compose plugin (`docker compose version` should work).
- An OIDC-compliant identity provider reachable from the backend (Keycloak, Entra ID, Okta, Authentik, ...). You'll need its issuer URL and a registered client ID/secret before first login.
- Enough disk for `bge-m3` (~1.2GB), the Docker images/build cache, and indexed repositories/documents. Add the size of an optional local LLM only on a suitably sized delivery host.

On Ubuntu 24.04, the verified package path was:

```sh
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
docker --version
docker compose version
```

Also verify that the Docker daemon is active and the installing user may access its socket (`docker info`).

## Hardware sizing

The current pilot baseline is **embedding-only** (`LLM_MODEL=disabled`). It fits the verified 4-vCPU/8GB CPU-only host and keeps ingestion, vector search and the knowledge graph usable, but it deliberately has no local chat generation or LLM-based compliance verdicts.

For a delivery that enables the validated Mistral NeMo 12B model, **16GB RAM / 8 vCPU is the minimum recommendation and a GPU is strongly preferred**. Its Q4 weights alone are ~7.5GB; CPU-only inference on the current small host would leave no safe headroom for concurrent users, parsing, Postgres vector indexing or the OS. Do not infer delivery sizing from the embedding-only idle figure above.

If the customer's hardware has an NVIDIA GPU, wiring it up (see "GPU passthrough (Ollama)" below) improves both load time and tokens/sec substantially — worth asking about during scoping, since it changes the sizing math and the "is this fast enough" first impression. This is **not** automatic: Docker never hands a container a GPU unless a compose file explicitly requests one, so an unmodified `docker-compose.yml`/`docker-compose.offline.yml` runs Ollama CPU-only even on a GPU box.

### Model mode: disabled pilot vs. delivery tiers

`LLM_MODEL=disabled` is the default until first delivery. Both `install.sh` and `scripts/build-offline-bundle.sh` then skip the chat/compliance model and pull only `bge-m3`.

On a suitably sized delivery host, set `LLM_MODEL=hf.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF:Q4_K_M` explicitly before installing. This validated Standard-Tier model is ~7.5GB and needs at least the 16GB RAM / 8GB+ VRAM class described above.

On 24GB+ VRAM hardware, set `LLM_MODEL=hf.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF:Q8_0` (~13GB) instead: `docs/COMPLIANCE_EVAL.md` (Befund 9/18/19/24/29) measures a consistently lower false-negative rate for the Code Compliance Checker on Q8_0 (12% vs. 24% on the largest test set), at identical false-positive rates and no measurable difference on general chat quality — the only cost is VRAM. This is a hardware-tier decision, not a license/feature tier: Q8_0 isn't gated behind anything, it just needs more VRAM than the 16GB-standard-tier host has to spare.

**Enabling or changing tiers on an existing deployment:** update `LLM_MODEL` in `.env`, pull the new tag (`docker exec doctus-ollama ollama pull <new-tag>`), then `docker compose up -d` (an env var change needs container recreation, not just a restart). Remove an old tag with `docker exec doctus-ollama ollama rm <old-tag>` if you want the disk space back.

### GPU passthrough (Ollama)

Neither `docker-compose.yml` nor `docker-compose.offline.yml` requests a GPU device for the `ollama` service by default — that's deliberate, so a CPU-only/dev host can install without the NVIDIA Container Toolkit present at all. GPU passthrough lives in a separate overlay, `docker-compose.gpu.yml`, layered on top via `COMPOSE_FILE` in `.env`.

**Host prerequisite** (once per GPU host, before installing): NVIDIA driver + the NVIDIA Container Toolkit, with its runtime registered with Docker:

```sh
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

`install.sh` and `install-offline.sh` both detect this automatically (`nvidia-smi` present **and** `docker info` lists the `nvidia` runtime) and set `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml` (or the offline equivalent) in `.env` — no manual step needed on a properly prepared GPU host, and every later `docker compose` command (including the "Enabling or changing tiers" step above and the "Updates later" step further down) then picks up the overlay automatically, no `-f` flags to remember.

To add it manually to an existing install (or if the toolkit was installed *after* the installer already ran once):

```sh
echo "COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml" >> .env   # or docker-compose.offline.yml for Path B
docker compose up -d
```

**Verify it actually took:**

```sh
docker exec doctus-ollama nvidia-smi        # lists the GPU from inside the container
docker exec doctus-ollama ollama ps         # PROCESSOR column should show GPU, not "100% CPU", once a model is loaded
```

**No GPU on this machine, but you still want chat/compliance to work for testing?** Don't chase GPU passthrough for that — use a cloud LLM profile instead: set `ALLOW_CLOUD_LLM=true` in `.env`, then add an OpenAI/Gemini/Anthropic profile with your API key under Settings > AI in the running app (per-browser, opt-in, no local model or GPU involved — see `CLAUDE.md`'s "Cloud nur als Opt-in"). Leave `LLM_MODEL=disabled`; it isn't needed for the cloud path.

## `.env` field reference

Copy `.env.example` to `.env` (both install scripts do this automatically if `.env` doesn't exist yet, generating the two secrets below).

| Var | Meaning |
|---|---|
| `DOCTUS_VERSION` | Tag used for the 3 custom-built images. Must match the version baked into an offline bundle if using Path B. |
| `COMPOSE_FILE` | Which compose files `docker compose` layers together. Empty on a CPU-only/dev host; set by the installers to include `docker-compose.gpu.yml` when a GPU is detected — see "GPU passthrough (Ollama)" above. |
| `LLM_MODEL` | `disabled` for the current embedding-only pilot (default) or for a CPU-only/dev host using a cloud LLM profile instead (see above), or an explicit Ollama tag for local chat + Code Compliance Checker on a suitably sized GPU delivery host. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | DB credentials, used by both the `db` service and the backend/parser's `DATABASE_URL`. |
| `API_URL` | Public URL the **frontend container** uses to reach the backend — read server-side at request time (`frontend/app/layout.tsx`), not baked into the image at build time. Set to whatever address the browser can reach the backend on. |
| `MASTER_ENCRYPTION_KEY` | Fernet key encrypting `KnowledgeSource.token` **and** document/chat content (`DocumentChunk.content`, `ChatMessage.content`, `ComplianceAlert.source_passage`/`discrepancy_description` — every connector's parsed content: Git, Confluence, Jira, Notion, IFC, DWG, GAEB, uploads) at rest, see `backend/models/crypto_types.py`. Generate: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Rotating this key requires re-encrypting all existing tokens and content first** — there's no automatic migration for that; treat it as fixed once you have real customer data. Losing this key makes the entire database's stored content permanently unreadable, not just connector credentials — back it up accordingly (see Backup section below). |
| `SESSION_SECRET_KEY` | Signs the app's own session cookie issued after OIDC login. Generate: `openssl rand -base64 32`. |
| `OIDC_ISSUER_URL` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | From the customer's IdP. Issuer URL must serve `/.well-known/openid-configuration`. |
| `OIDC_REDIRECT_URI` | Register this exact URI as an allowed redirect URI on the IdP client — typically `<API_URL>/auth/callback`. |
| `FRONTEND_URL` | Used for CORS (`allow_origins`) — must be the exact origin the browser loads the frontend from. |
| `LOG_LEVEL` | Backend log verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`), default `INFO`. The parser worker's verbosity is set separately via `--loglevel` on its `celery` command (`parser/Dockerfile`), not by this var. |
| `ADMIN_EMAILS` | Comma-separated list, matched case-insensitively against the OIDC `email` claim. Grants admin: bypasses team-based visibility, manages teams/members. No separate admin-bootstrap UI — set this before first login for whoever should be the customer's first admin. |

## TLS

Doctus itself doesn't terminate TLS — `backend-api`/`frontend` listen on plain HTTP (ports 8000/3000), consistent with the project's "no extra infra beyond what's needed" stance (same reasoning as no bundled Kubernetes/Helm). Given the ICP this is built for (regulated/compliance-driven customers), **don't run a real deployment without HTTPS in front of it**: the session cookie set after OIDC login is only marked `Secure` (backend/api/auth.py) when `FRONTEND_URL` starts with `https://` — over plain HTTP, anyone on the network path can read it.

Put a reverse proxy the customer already trusts (or already runs) in front of both ports and terminate TLS there. Example with Caddy, picked for its automatic cert handling — substitute whatever the customer's infra team standardizes on (nginx, Traefik, an existing load balancer):

```
your-doctus-domain.example.com {
    reverse_proxy /auth/* localhost:8000
    reverse_proxy /* localhost:3000
}
```

Then set `FRONTEND_URL=https://your-doctus-domain.example.com`, `API_URL` to whatever address the frontend container reaches the backend on, and `OIDC_REDIRECT_URI` to the `https://` callback URL registered with the IdP.

> **The #1 way a fresh install ends up with broken login:** `FRONTEND_URL`, `API_URL`, and `OIDC_REDIRECT_URI` all default to `localhost` in `.env.example`. That only works if the browser you're testing with runs on the *same machine* as the Docker host. As soon as you (or the customer) open Doctus from another machine against the server's IP/hostname, `localhost` in all three breaks differently but simultaneously: the frontend's API calls get CORS-rejected (`FRONTEND_URL` no longer matches the real browser origin), and the post-login redirect from the IdP goes nowhere (it's the *browser* navigating to `OIDC_REDIRECT_URI`, not the backend, so `http://localhost:8000/auth/callback` sends the browser to look for a server on its own machine). Set all three to the server's actual reachable address before the first real login attempt, not just `API_URL` — and remember `.env` edits need `docker compose up -d` (not `docker compose restart`) to actually take effect, since Compose only injects env vars at container creation.

## No IdP available yet? Throwaway Keycloak for testing

For scoping/demo/smoke-testing a fresh install before the customer's real IdP is wired up, spin up a disposable Keycloak using the same realm CI uses (`.github/keycloak/doctus-realm.json` — a `doctus` realm with a `doctus-backend` client and a `testuser`/`testpass` user). **Test-only — never point this at real customer data; the client secret and user password are public in this repo.**

The realm sets `loginTheme: doctus`, a small custom theme (`.github/keycloak/themes/doctus/`) that skins Keycloak's login page to match the Doctus frontend (dark glass card, gradient button, logo — see `frontend/components/LoginView.tsx`) instead of stock Keycloak red, so a scoping demo doesn't visually context-switch between the two. It only affects this throwaway IdP; a customer's own IdP keeps its own branding. Mount it alongside the realm import:

```sh
docker run -d --name test-keycloak -p 8080:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  -v "$(pwd)/.github/keycloak:/opt/keycloak/data/import" \
  -v "$(pwd)/.github/keycloak/themes/doctus:/opt/keycloak/themes/doctus" \
  quay.io/keycloak/keycloak:25.0 start-dev --import-realm
```

Wait for it to be ready before touching `.env` (first boot takes a few seconds):

```sh
until curl -sf http://localhost:8080/realms/doctus/.well-known/openid-configuration >/dev/null; do sleep 2; done
```

### Picking `<server-address>`

Every URL below must use the **same** `<server-address>`, and it has to be reachable from two different places, not just one:

- the **browser** you log in with (obviously), and
- the **`backend-api` container itself** — it does its own server-to-server calls to `OIDC_ISSUER_URL` (OIDC discovery + the authorization-code→token exchange in `backend/core/oidc.py` / `backend/api/auth.py`), independent of whatever the browser can reach.

This is where `localhost` quietly breaks even when the browser *is* on the Docker host: `localhost` inside the `backend-api` container refers to the container itself, not your host, so the discovery call fails to connect. Pick based on your case:

| Case | `<server-address>` | Why it works for both sides |
|---|---|---|
| Testing from a browser on a **different machine** than the Docker host (the common case) | The server's real LAN/public IP, e.g. `192.168.1.50` or `82.165.216.180` | The browser reaches it normally; the container reaches it too via hairpin NAT back through the host's own interface (verify with `docker exec doctus-backend python3 -c "import httpx; print(httpx.get('http://<server-address>:8080/realms/doctus/.well-known/openid-configuration').status_code)"` — expect `200`) |
| Testing from a browser on the **same machine** as the Docker host | The Compose network's gateway IP, **not** `localhost` — find it with `docker network inspect doctus_default --format '{{(index .IPAM.Config 0).Gateway}}'` (typically `172.18.0.1`; project prefix may differ if you cloned into a differently-named folder) | That gateway IP is reachable both from the container (it's the container's default route to the host) and from the host itself (it's one of the host's own bridge interfaces) |

Once you have it, register it on the Keycloak client — the realm file only ships `http://localhost:8000/auth/callback` / `http://localhost:3000` by default. Either click through the admin console (`http://<server-address>:8080`, admin/admin → Clients → `doctus-backend` → Settings → add to *Valid redirect URIs* / *Web origins*), or patch it in one shot via the admin API:

```sh
TOKEN=$(curl -s -X POST "http://localhost:8080/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" -d "username=admin" -d "password=admin" -d "grant_type=password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
CLIENT_UUID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/admin/realms/doctus/clients?clientId=doctus-backend" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/admin/realms/doctus/clients/$CLIENT_UUID" \
  | python3 -c "
import json, sys
c = json.load(sys.stdin)
c['redirectUris'] = list(set(c['redirectUris'] + ['http://<server-address>:8000/auth/callback']))
c['webOrigins'] = list(set(c['webOrigins'] + ['http://<server-address>:3000']))
json.dump(c, open('/tmp/kc-client.json', 'w'))
"
curl -s -o /dev/null -w "%{http_code}\n" -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d @/tmp/kc-client.json "http://localhost:8080/admin/realms/doctus/clients/$CLIENT_UUID"   # expect 204
```

Then set, using that same `<server-address>` consistently:

```
OIDC_ISSUER_URL=http://<server-address>:8080/realms/doctus
OIDC_CLIENT_ID=doctus-backend
OIDC_CLIENT_SECRET=ci-only-keycloak-client-secret
OIDC_REDIRECT_URI=http://<server-address>:8000/auth/callback
API_URL=http://<server-address>:8000
FRONTEND_URL=http://<server-address>:3000
ADMIN_EMAILS=testuser@example.com
```

`ADMIN_EMAILS` is what makes `testuser` an admin on first login (see the `.env` field reference above) — the realm doesn't carry any app-level role by itself, only the identity Doctus's backend then matches against this list. `docker compose up -d` to apply (Compose only injects env vars at container creation, so this step is required even though nothing in the images changed), then log in at `http://<server-address>:3000` as `testuser` / `testpass`.

Firewall note: this throwaway Keycloak has its password and client secret sitting in plain sight in this repo. If `<server-address>` is a real public IP, don't leave port `8080` (or `3000`/`8000`) open to the internet longer than the demo needs — check `ufw status` / `iptables -L INPUT` before walking away from the box. The verified fresh-host run found UFW inactive; that was acceptable only for the short smoke test, not as a hand-off state. Replace this IdP and add TLS/firewall policy before real customer data is introduced.

## Path A — Online install

Use this when the customer's server has internet access during setup.

```sh
git clone --branch main --single-branch <repo> Doctus && cd Doctus
./install.sh
```

`main` is the customer-deployment branch; the fresh-host evaluation recorded above was deliberately performed on `develop`. The installer checks for Docker, bootstraps `.env`, builds each distinct custom image serially, starts Compose (Alembic migrations run automatically on backend startup), and pulls `bge-m3`. It pulls a local chat/compliance model only when `LLM_MODEL` is explicitly set to a tag other than `disabled`.

Updates later: `git pull && docker compose build backend-api && docker compose build parser-worker && docker compose build frontend && docker compose up -d`. Keeping the builds serial avoids the shared parser-worker/parser-beat image export race seen with Docker 29. An install carrying data from before the content-at-rest encryption fix (see `.env` field reference above) runs a one-time Alembic data migration on this restart that re-encrypts any plaintext still sitting in `document_chunks`/`chat_messages`/`compliance_alerts` — batched, so it's safe on a large table, but a very large existing install may take noticeably longer to come up on that first restart.

Before running this, set `DOCTUS_VERSION` in `.env` to a real, unique value (e.g. the git short SHA you're upgrading to) instead of leaving the `.env.example` default `latest` — a `latest`-tagged build silently overwrites the previous image with nothing kept to roll back to. See **Rollback** below.

## Optional demo/test projects

These synthetic fixtures are for evaluation and demos only. Do not seed them into a customer database. Set `WATCHED_FOLDER` in `.env` to the absolute host path of this checkout's `watched/` directory before starting Compose; relative or empty values do not mount the bundled files.

The parser image intentionally contains parser runtime code, not root-level maintenance scripts, so copy the current scripts in and run them explicitly:

```sh
docker cp scripts/demo_project_data.py doctus-parser:/app/demo_project_data.py
docker cp scripts/seed_demo_architektur.py doctus-parser:/app/seed_demo_architektur.py
docker cp scripts/compute_embeddings_and_ifc_chunks.py doctus-parser:/app/compute_embeddings_and_ifc_chunks.py

docker exec doctus-parser python /app/seed_demo_architektur.py
docker exec doctus-parser python /app/compute_embeddings_and_ifc_chunks.py
```

The first script is idempotent. The embedding script rebuilds the three synthetic IFC compliance chunks and embeds all demo chunks through `bge-m3`; it does not invoke a chat LLM. On the verified run, expected data was:

- 3 projects: GFZ Potsdam, Interimsbüro Containeranlage Nord, and Lindenhof Holdout.
- 6 knowledge sources, 24 document chunks, 31 IFC entities, and 31 entity-document links.
- All 24 embeddings non-null and 1024-dimensional.

Verify instead of trusting the script's exit code:

```sh
docker compose ps
curl -fsS http://localhost:8000/health
docker exec doctus-ollama ollama list       # pilot: bge-m3 only
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" -c \
  "SELECT count(*) projects FROM projects; \
   SELECT count(*) chunks, count(*) FILTER (WHERE embedding IS NULL) missing_embeddings \
   FROM document_chunks;"
```

Re-running `seed_demo_architektur.py` should report the existing rows and finish without missing-file warnings. A warning for `Brandschutzkonzept_Lindenhof.pdf` means the checkout predates the completed third fixture or `WATCHED_FOLDER` points at the wrong directory.

## Path B — Air-Gapped / Offline Installation

Use this when the customer's server has **no internet/registry egress at all** — common for the privacy-strict, on-prem customers Doctus is positioned for. Here, the consultant builds and exports everything on a connected machine; the customer machine only loads and runs.

### Who runs what

| Step | Run by | Where |
|---|---|---|
| Build bundle | Consultant | Any machine with internet + this repo + Docker |
| Transfer bundle | Consultant | Your own secure channel — not scripted, pick whatever fits the engagement (encrypted USB, SFTP to a customer-controlled endpoint, etc.) |
| Install | Customer (or you, on-site) | The air-gapped target machine |

### 1. Build the bundle

```sh
./scripts/build-offline-bundle.sh [version]
```

`version` defaults to the current short git SHA. Output: `dist/doctus-offline-bundle-<version>/`, containing:

- `images.tar.gz` — `docker save` of all 6 images: the 3 custom-built ones (`doctus-backend-api`, `doctus-parser-worker`, `doctus-frontend`) plus the pinned-by-digest base images (`ankane/pgvector`, `valkey/valkey:8-alpine`, `ollama/ollama`) — Redis was replaced by its permissively-licensed fork Valkey, see `docker-compose.yml`. Pinning by digest means a bundle rebuilt later reproduces the exact same base images rather than silently drifting with upstream `:latest`.
- `ollama-models.tar.gz` — a **clean** pull of `bge-m3` plus the explicitly configured `LLM_MODEL`, if enabled (not a copy of any existing `./data/ollama`, which may carry stale/unused models from prior local testing).
- `docker-compose.offline.yml`, `docker-compose.gpu.yml` (GPU overlay, see "GPU passthrough (Ollama)" above), `.env.example` (pre-filled with the matching `DOCTUS_VERSION`), `install-offline.sh`, this doc.
- the AP-9 license/provenance artifact generated from the shipped lockfiles,
  images, and model manifest; it must travel with the air-gapped bundle.
- `MODEL_MANIFEST.txt` — the actual pulled model names/digests/sizes for this specific build (captured via `ollama list` at build time), plus the quantization-provenance note for the LLM tag. Lets a customer verify exactly which model artifact they received against the upstream Hugging Face repo, independent of `SHA256SUMS` (which only proves the bundle's own internal integrity, not where the weights originally came from).
- `SHA256SUMS` — covers every file in the bundle, checked by `install-offline.sh` before anything is loaded.

Size depends on `LLM_MODEL`. Even the embedding-only bundle is dominated by the large Ollama base image and build images; enabling Q4 adds another ~7.5GB. Measure the generated directory with the script's final `du -sh` output rather than relying on an old fixed estimate.

**Same CPU architecture is assumed** between the build machine and the customer's target (both x86_64 today). A customer on a different architecture (e.g. ARM) needs a rebuild with `docker buildx --platform`, which isn't currently scripted.

### 2. Install on the customer machine

Extract the bundle, then:

```sh
./install-offline.sh
```

This verifies `SHA256SUMS`, `docker load`s the images, restores the Ollama models into `./data/ollama`, bootstraps `.env` (same logic as Path A), and runs `docker compose -f docker-compose.offline.yml up -d` — no build step, no registry access at any point.

### 3. Updating later

There's no `git pull` on an air-gapped box. Updates mean repeating the full cycle: bump the code, re-run `build-offline-bundle.sh` with a new version, transfer the new bundle, run `install-offline.sh` again on the customer side (it's safe to re-run — it skips `.env` bootstrap if one already exists, and `docker load`/`docker compose up -d` simply replace the running containers with the new image tags).

Unlike Path A, each bundle already tags its images with its own `DOCTUS_VERSION` (never `latest`), and `docker load` adds images without deleting differently-tagged ones already on the host — so the previous version's images normally stay available locally for rollback even without keeping the old bundle around. See **Rollback** below.

If a `MASTER_ENCRYPTION_KEY` rotation is ever needed on an already-deployed customer instance, existing encrypted tokens must be re-encrypted first — same trap as on the online path, just harder to fix remotely. Avoid rotating it casually once real data exists.

## Backup

Single-tenant self-host means there's no managed backup behind the scenes — it's the customer's (or your, if you operate the box) responsibility. Three things need backing up; everything else is reproducible.

| Path | Why it matters | Reproducible without a backup? |
|---|---|---|
| `data/postgres` | All repository/entity/chunk/embedding data, knowledge sources, links, topics, chat history, users. | No — full reparse of every repo from scratch. |
| `./repos` (includes `./repos/uploads`) | Git checkouts (re-clonable from origin) **and** locally-uploaded documents (`upload_local_document`), which exist nowhere else. | Partially — git checkouts yes, uploaded files no. |
| `.env` | All secrets, especially `MASTER_ENCRYPTION_KEY`. | No — losing this key makes every encrypted `KnowledgeSource.token` **and every stored document/chat content column** permanently undecryptable, independent of whether Postgres itself is intact. |

`data/ollama` (the model weights) is normally **not** worth backing up — both install paths can restore `bge-m3` and any explicitly configured delivery LLM. The embedding-only pilot has only `bge-m3` here.

**Back up** (Postgres can be dumped live, no need to stop the stack):
```sh
docker compose exec -T db pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > doctus-db-$(date +%F).sql.gz
tar czf doctus-repos-$(date +%F).tar.gz ./repos
cp .env doctus-env-$(date +%F).bak
```

**Restore** (fresh host, or after wiping a broken one):
```sh
git clone <repo> && cd Doctus
cp doctus-env-<date>.bak .env
docker compose up -d db          # creates the empty doctus DB/role from .env
gunzip -c doctus-db-<date>.sql.gz | docker compose exec -T db psql -U ${POSTGRES_USER} ${POSTGRES_DB}
tar xzf doctus-repos-<date>.tar.gz
docker compose up -d
```

Store the `.env` backup at least as securely as the live server — combined with a Postgres dump it fully decrypts every stored credential. Back up before every version upgrade at minimum; beyond that, follow the customer's existing backup cadence for self-hosted systems.

## Rollback

**Prerequisite:** a `.env` + Postgres dump backup taken *before* the upgrade (see **Backup** above — this is why "back up before every version upgrade" is not optional). Without it, rollback below is code-only and will not undo any data an already-migrated schema wrote.

**Path A (online):** rolling back means pointing `DOCTUS_VERSION` in `.env` at the previous value and running `docker compose up -d` — no rebuild, so this only works if that previous image is still present locally (`docker images | grep doctus-`). This is why the "Updates later" step above says to set `DOCTUS_VERSION` to a real, unique value before building: a build left on the `latest` default overwrites the only copy of the prior image, and by the time a problem surfaces there is nothing left to roll back to.

**Path B (offline):** same idea, but each bundle already carries its own `DOCTUS_VERSION` tag and `docker load` doesn't delete older tags — so `DOCTUS_VERSION=<previous-version>` in `.env` + `docker compose -f docker-compose.offline.yml up -d` is normally enough, without needing the old bundle directory again — as long as no one has since run `docker image prune`.

**The part image rollback does not cover: the database.** Alembic migrations run automatically on every container start and are forward-only — there is no shipped `alembic downgrade` path, and manually downgrading against real customer data is not something to improvise under pressure. If the version you're rolling back from already ran a migration (check `docker compose logs backend-api` for Alembic output on that start), the old code image will not match the new schema. In that case, code rollback alone is not sufficient:

1. Stop the stack: `docker compose down` (keeps volumes).
2. Restore the pre-upgrade Postgres dump and `.env` from the **Backup** section above (this discards any data written between the upgrade and the rollback — there is no way around that without the dump).
3. Roll back `DOCTUS_VERSION` as described for Path A/B.
4. `docker compose up -d` and re-verify with the same health checks used after a fresh install (`docker compose ps`, `curl -fsS http://localhost:8000/health`).

**Before the pilot:** rehearse one full upgrade → rollback cycle on disposable data (e.g. the demo project, not real Dömges data) so this isn't the first time it's attempted under a real incident.

## Troubleshooting

**Login button does nothing / backend returns a 500 on `/auth/login`.** Check `docker compose logs backend-api` for `httpx.UnsupportedProtocol: Request URL is missing an 'http://' or 'https://' protocol` — that's `OIDC_ISSUER_URL` (and usually `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` too) still blank in `.env`. The install scripts print a warning for this right after starting the stack (`check_env_ready` in `scripts/lib/env-bootstrap.sh`) — if you missed it scrolling past, that's the bug it's flagging. Fill in real IdP details (or see "No IdP available yet?" above), then `docker compose up -d` to apply.

**Login redirects to the IdP fine, but never makes it back / browser console shows CORS errors / the post-login redirect tries to load `localhost`.** `FRONTEND_URL`, `API_URL`, and/or `OIDC_REDIRECT_URI` are still set to `localhost` while the browser is on a different machine than the Docker host — see the callout under "TLS" above. Set all three to the server's real address, update the redirect URI/web origin registered on the IdP client to match, then `docker compose up -d`.

**Changed `.env` but nothing changed.** `docker compose restart` does not re-read `.env` — Compose only injects environment variables when a container is *created*. Use `docker compose up -d`, which recreates only the containers whose config actually changed.

**Build fails with `image "doctus-parser-worker:<tag>" already exists`.** This is the Docker 29 parallel-export race from older checkouts where `parser-worker` and `parser-beat` both build the same tag. Pull the installer fix or build distinct images serially: `docker compose build backend-api`, `docker compose build parser-worker`, `docker compose build frontend`, then `docker compose up -d --no-build`.

**Chat/compliance says the local Ollama LLM is disabled.** This is expected on the current 4-vCPU/8GB CPU-only pilot. `bge-m3` still supports ingestion and vector search. Do not point chat at `bge-m3`; it is an embedding model, not a generator. Enable an explicit `LLM_MODEL` only after moving to appropriately sized hardware, pull that tag, and recreate the affected containers with `docker compose up -d`.

## Monitoring

No monitoring stack ships with Doctus — that would be over-engineering for a single-tenant box (see the no-Kubernetes decision above). Point whatever the customer already runs (Nagios, Zabbix, Prometheus blackbox exporter, or just cron + curl) at:

- **Backend liveness:** `GET <API_URL>/health` → `{"status": "healthy", "checks": {"database": "ok", "redis": "ok", "ollama": "ok"}}` on success. Since `docs/DIAGNOSTICS_HARDENING.md` #4, this is a real readiness check — it pings Postgres/Redis/Ollama directly and returns HTTP 503 with the failing entry named in `checks` if any of them is unreachable, so a single `curl` here is enough to catch a wedged dependency.
- **Container status:** `docker compose ps` — every service in `docker-compose.yml` now has a `healthcheck:` block, so a wedged-but-running container shows `(unhealthy)` here, not just plain `Up`; a genuinely crashed one still cycles through `Restarting` (every service is on `restart: always`), and neither state pages anyone on its own.
- **Dependency reachability**, for manual double-checking or when `/health` itself is unreachable:
  ```sh
  docker compose exec redis redis-cli ping
  docker compose exec db pg_isready -U ${POSTGRES_USER}
  curl -sf http://localhost:11434/api/tags >/dev/null && echo ollama-ok
  ```
- **Logs:** `docker compose logs -f <service>` for ad hoc debugging. Every service is capped at 10MB × 3 files via the `x-logging` anchor in `docker-compose.yml`/`docker-compose.offline.yml` — Docker's `json-file` driver has no size cap by default, and these containers run indefinitely on a customer's box.
- **Disk usage:** `data/postgres` and `./repos` are the two that grow with usage (CAD/BIM models and document repositories can be large). Not Doctus-specific — alert on free disk space the same way you would for any self-hosted service.

## Diagnostics bundle

**Before restarting or redeploying anything to "fix" a reported problem, run `python scripts/generate_diagnostics.py` from the repo root.** Logs are capped at 10MB × 3 files per service (see above) and a container restart clears its in-memory log buffer immediately — either way, whatever evidence explains the problem is gone the moment you act on it instead of capturing it first.

The script collects, into a single `doctus-diagnostics-<timestamp>.tar.gz` in the current directory:
- System specs (OS, CPU, memory, disk, GPU) and Docker/Compose versions.
- Container status (`docker compose ps -a`) and image IDs (`docker compose images`), so you can tell whether a customer's install is actually running the build you think it is.
- The last 2000 lines of every service's logs, including `frontend`.
- Sanitized `.env` (secrets replaced with `[REDACTED]`).
- Repository/knowledge-source sync state, `compliance_alerts` and `compliance_runs` rows, summary row counts, and the applied Alembic schema revision (`alembic current`) — all read directly from Postgres, skipped gracefully if the `db`/`backend-api` containers are down.
- Loaded Ollama models.

It deliberately does **not** dump `document_chunks` or `chat_messages` (actual customer document/BIM content and chat text) — only metadata about sync state and schema. Safe to send for troubleshooting as-is.
