# Doctwos — Legacy Code Intelligence Workspace

> **Proprietary — restricted use.** Doctwos is private, closed-source software.
> No permission is granted to use, copy, modify, deploy, or redistribute this
> repository without prior written consent from the project owner.

Doctwos is a self-hosted workspace for understanding large legacy codebases. Its
current product focus is COBOL: repositories are indexed, parsed into structural
entities and relationships, and made explorable through code views, contextual
chat, references, knowledge graphs, and call graphs.

## Current implementation status

Work packages **AP-0 through AP-7 are complete**. The remaining planned work is:

- **AP-8:** connector follow-up and regression coverage for upload, Confluence,
  Jira, WebDAV, and FolderWatch.
- **AP-9:** load testing, accessibility/BITV, release hardening, offline bundle,
  and final documentation.

See [open development points](docs/OFFENE_ENTWICKLUNGSPUNKTE.md),
[technical plan](docs/IMPLEMENTIERUNGSPLAN.md), and
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
password is printed once in the backend startup log.

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

The Python test suites use separate dependency environments. Three embedding
tests require a running Ollama instance with `bge-m3`; they are skipped when it
is unavailable.

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
- `parser/cobol_persist.py` — entity and edge persistence
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
