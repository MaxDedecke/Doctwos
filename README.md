# Doctwos — Legacy Code Intelligence Workspace

> **Proprietary — restricted use.** Doctwos is private, closed-source software.
> No permission is granted to use, copy, modify, deploy, or redistribute this
> repository without prior written consent from the project owner.

Doctwos is a self-hosted workspace for understanding large legacy codebases. Its
current product focus is COBOL: repositories are indexed, parsed into structural
entities and relationships, and made explorable through code views, contextual
chat, references, knowledge graphs, and call graphs.

## Current implementation status

The implementation work packages are complete. Remaining product decisions,
external acceptance work, and follow-up improvements are tracked in
[open development points](docs/OFFENE_ENTWICKLUNGSPUNKTE.md). See also the
[access-control model](docs/ACCESS_CONTROL.md) and
[design guidelines](docs/DESIGN_GUIDELINES.md).

## Product capabilities

### COBOL intelligence

- Fixed- and free-format COBOL parsing, including continuations and embedded SQL
- Programs, copybooks, sections, paragraphs, data items, file descriptions, and
  SQL blocks as navigable entities
- CALL, PERFORM, GOTO, COPY, READS, WRITES, and USES relationships
- Cross-copybook reference resolution and explicit unresolved/dynamic edges
- Golden-file parser corpus and fallback indexing for malformed source files

### Repository and knowledge ingestion

- GitHub, GitLab, Bitbucket, and generic Git repositories
- Branch-isolated bare mirrors and worktrees for monorepos
- Resumable file-level synchronization
- Confluence, Jira, WebDAV, FolderWatch, and local upload sources
- OCR fallback for scanned documents

### Workspace

- Configurable one- to four-panel workspace
- Monaco code inspection with persistent line references in chat
- Focus objects and grouped inbound/outbound references
- Call graph with one to three hops, edge filters, and JSON/CSV/GraphML export
- Global search, knowledge graph, link manager, topics, and job center
- German and English UI, light/dark themes, and responsive navigation

### Security and operation

- Local username/password authentication with Argon2id hashes
- Bootstrap superuser and administrative user management
- Mandatory password change for newly provisioned accounts
- Login throttling, temporary account locks, reset, and unlock flows
- Team- and project-scoped authorization
- Local Ollama inference by default; cloud providers fail closed unless enabled
- Sanitized diagnostics, bounded logs, health checks, and encrypted connector secrets

## Architecture

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 18, Tailwind CSS, Monaco Editor |
| Backend | FastAPI, SQLAlchemy, Alembic |
| Workers | Celery |
| Queue/cache | Valkey 8, Redis-compatible |
| Database | PostgreSQL with pgvector |
| Local AI | Ollama and BGE-M3; optional configured chat model |
| Authentication | Local signed HTTP-only session cookies |

The Compose stack contains seven services: `frontend`, `backend-api`,
`parser-worker`, `parser-beat`, `db`, `redis`, and `ollama`.

## Getting started

### Requirements

- Linux host
- Docker Engine and Docker Compose
- sufficient storage for images, models, mirrors, worktrees, and indexed content

### Storage requirements & sizing benchmarks

Based on an empirical benchmark of a medium-sized project (**JUnit 5 framework**: 2,363 files, 2,332 parsed code files, 1 PDF documentation source):

| Component | Storage used | Notes |
|---|---|---|
| **PostgreSQL (`./data/postgres`)** | **~765 MB** *(613 MB internal DB)* | 29,899 vector chunks, 141,340 callgraph edges |
| **Repositories & Uploads (`./repos`)** | **~68 MB** | Bare Git mirrors, AST worktrees, and document uploads |
| **Application Logs (`./data/logs`)** | **~119 MB** | Bounded logs (backend, parser worker, beat, frontend) |
| **Local Embedding Model (`./data/ollama`)** | **~1.1 GB** | `bge-m3` weights (*0 MB if using remote embeddings*) |
| **Total Project Ingestion Data** | **~2.05 GB** | *(~950 MB when using external/remote embeddings)* |
| **Docker Images (Doctus Core)** | **~3.7 GB** | Frontend, Backend API, Parser Worker, Valkey, pgvector |
| **Docker Image (Ollama runtime)** | **~8.25 GB** | Ollama runtime with CUDA/GPU support (*only if local AI active*) |
| **Total Runtime Footprint** | **~14.0 GB** | *(~4.7 GB with external LLM/embedding endpoint)* |

#### Database internals breakdown (613 MB)

- **`document_chunks` (408 MB total)**:
  - **210 MB**: HNSW vector index (`idx_document_chunks_embedding_1024_hnsw`, 1024 dimensions)
  - **~161 MB**: TOAST storage (vector arrays and chunk text)
  - **37 MB**: Table rows (29,899 chunks)
- **`code_edges` (116 MB total)**: 141,340 call-graph edges, class hierarchies, imports, and references
- **`knowledge_links` (56 MB total)**: Cross-source concept and document links
- **`code_entities` (20 MB total)**: 23,594 structural entities (classes, interfaces, methods)
- **File & session metadata (~2 MB)**: Scan files, chat sessions, audit logs

#### Capacity planning rule of thumb

- **Per medium project (~2,000–3,000 files, ~25,000 entities)**: Expect **600 MB–1 GB** in PostgreSQL (primarily driven by 1024-dim HNSW indexing and structural callgraph edges) and **~1.0–1.5×** the repository size in `./repos`.
- **Recommended Host Disk Space**:
  - **Local/Air-gapped (Ollama on-prem)**: Minimum **25–30 GB SSD** (images ~12 GB + models 2–5 GB + database and repos + build/log headroom).
  - **Cloud/Remote Inference (OpenAI / Azure / RunPod)**: **10–15 GB SSD** is sufficient for multiple medium projects.


### Installation

```bash
git clone https://github.com/MaxDedecke/Doctwos.git
cd Doctwos
cp .env.example .env
```

Set secure values in `.env`, especially:

```dotenv
POSTGRES_PASSWORD=<secure-password>
MASTER_ENCRYPTION_KEY=<fernet-key>
SESSION_SECRET_KEY=<random-secret>
BOOTSTRAP_SUPERUSER=admin
BOOTSTRAP_SUPERUSER_PASSWORD=<optional-start-password>
API_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
```

If `BOOTSTRAP_SUPERUSER_PASSWORD` is empty on a fresh database, the generated
password is printed once in the backend startup log. The online and offline
installers also display these generated credentials directly after starting the
services (waiting up to 120 seconds). Save them securely and change the password
at first login; do not share the installer output or bootstrap log. On updates,
existing credentials remain unchanged and old passwords are not displayed again.
An explicitly configured bootstrap password is never printed by the installer.
If startup cannot be confirmed in time, the installer points to
`docker compose logs backend-api` for diagnosis.

Start the application with:

```bash
./install.sh
```

Default endpoints:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Ollama: `http://localhost:11434` (loopback only)

Production deployments must place a trusted TLS reverse proxy in front of the
frontend and backend.

## Development

Frontend:

```bash
cd frontend
npm ci
npm run build
npm test
```

Backend and parser tests:

```bash
cd backend && python -m pytest tests/
cd ../parser && python -m pytest tests/
```

DB-backed parser integration tests can also run in the Compose network. This
uses the current workspace source and the existing `db`/`redis` services, so
the host does not need direct PostgreSQL credentials:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile test \
  run --rm parser-test python -m pytest tests/test_t51_integration.py -q
```

The Python test suites use separate dependency environments. Three embedding
tests require a running Ollama instance with `bge-m3`; they are skipped when it
is unavailable.

Python lint and formatting (from the repository root, in a development venv):

```bash
python -m pip install -r requirements-lint.txt
python -m ruff check backend parser
python -m ruff format --check backend parser
```

CI runs both checks in the `python-quality` job. Run `python -m ruff format
backend parser` to apply formatting locally. `ruff.toml` pins the tool version,
targets Python 3.11, and enables import/statement checks (`E4`, `E7`, `E9`)
and Pyflakes (`F`). Tests and migrations are included. Generated ANTLR sources
are excluded; router imports after logging
setup in `backend/main.py` have a specific `E402` exception. Ruff does not
replace pytest or provide mypy-style type checking.

## Repository structure

```text
frontend/   Next.js workspace and UI components
backend/    FastAPI APIs, auth, RAG, graph retrieval, and migrations
parser/     Celery workers, connectors, COBOL parser, and persistence
config/     Runtime feature configuration
scripts/    Installation, diagnostics, and delivery tooling
docs/       Plan, status, decisions, operations, and security documentation
```

Important entry points:

- `parser/cobol/parse.py` — COBOL parser orchestration
- `parser/connectors/git.py` — resumable Git ingestion
- `parser/structure_persist.py` — entity and edge persistence
- `backend/api/auth.py` — local authentication
- `backend/api/entities.py` and `backend/api/callgraph.py` — graph APIs
- `frontend/app/page.tsx` — workspace orchestration
- `frontend/components/CallGraphView.tsx` — call graph UI
- `frontend/components/LoginView.tsx` — local login and password change

## Branding

Doctwos uses the “Structured Intelligence” design system: restrained technical
surfaces, editorial hierarchy, Fujitsu red for focus, and a controlled red-to-blue
brand gradient for primary actions and identity surfaces. The binding rules are in
[DESIGN_GUIDELINES.md](docs/DESIGN_GUIDELINES.md).

## License

All rights reserved. Third-party components and model weights retain their
respective licenses and distribution obligations.
