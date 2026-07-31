# Doctus — Local AI Knowledge System for AEC

> **Proprietary — restricted use.** Doctus is private, closed-source software. No permission is granted to use, copy, modify, deploy, or redistribute this repository or its source code without prior written consent from the project owner. Third-party components and AI models keep their respective licenses; see [Open-source clearing](docs/OPEN_SOURCE_CLEARING.md).

Doctus is a local-first knowledge and review assistant for the Architecture, Engineering, and Construction (AEC) industry. It connects BIM/CAD models, project documents, technical rules, HOAI context, repositories, and collaboration systems through one searchable workspace.

The default deployment runs on the customer's own infrastructure with Ollama. Optional cloud LLM profiles can be enabled explicitly, but are disabled by default. Compliance results are **decision-support signals**: a qualified professional must review and confirm every finding before it is used.

## Current product scope

### AEC knowledge and review

- **Project-aware RAG:** Search and chat across PDFs, DOCX files, email exports, logs, repositories, and indexed project documents with clickable source references.
- **BIM/CAD understanding:** Parse IFC entities and property sets, render IFC models in 3D, and convert DXF drawings for 2D viewing.
- **Compliance checker:** Compare IFC properties with retrieved project requirements. The current registry includes fire-safety and acoustic checks.
- **Auditable findings:** Compliance runs and alerts retain the cited document, verbatim source passage, extracted required class, and run history; CSV export is available.
- **HOAI copilot:** Surface phase-aware checklists and relevant project context for LPH 1–9.
- **Knowledge links and topics:** Connect documents, design entities, code objects, and related project knowledge with a review workflow.
- **OCR and AEC formats:** OCR fallback for scanned PDFs, GAEB XML import, IFC parsing through IfcOpenShell, and DXF parsing through ezdxf.

### Enterprise operation

- **Local-first / air-gapped deployment:** Online installer and reproducible offline bundle for isolated customer environments.
- **Team and project access control:** OIDC authentication, admin bootstrap, team membership, and project-scoped visibility.
- **Knowledge connectors:** Scheduled delta sync for network folders, Confluence, Jira, and Notion (with optional recursive subpage crawling), including supported attachments.
- **Optional MCP tools:** Live connector access during agentic chat when the optional Node.js runtime is included.
- **LLM profiles:** Local Ollama profiles plus explicitly enabled OpenAI, Anthropic, and Gemini profiles.
- **Operational tooling:** Health checks for all services, bounded container logs, version reporting, backup guidance, and a sanitized diagnostics bundle.

### Workspace

The frontend provides a modular multi-panel workspace with:

- conversational search and source navigation,
- Monaco-based document/code inspection,
- 3D BIM and 2D CAD viewers,
- knowledge graph and topic views,
- repository browser and Git setup wizard,
- shareable chat-session URLs,
- configurable 1-, 2-, 3-, and 4-panel layouts.

See [Feature reference](docs/FEATURES.md) for the detailed implementation status.

## AI stack and model decision

The current CPU-only pilot defaults to embedding-only mode; the validated delivery LLM remains opt-in:

| Role | Model | Notes |
|---|---|---|
| Chat and structured extraction | Disabled by default; optional `hf.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF:Q4_K_M` | Validated 12B delivery model, approximately 7.5 GB, for suitably sized hardware |
| Embeddings | `bge-m3` | 1024-dimensional multilingual embeddings, MIT license |
| Runtime | Ollama | Local inference through the native chat and embedding APIs |

When enabled, use the exact evaluated Q4_K_M tag above rather than Ollama's generic `mistral-nemo` tag. See [Deployment](docs/DEPLOYMENT.md) for the `LLM_MODEL=disabled` pilot default and delivery sizing.

### Evaluation status

The compliance pipeline uses LLM-based requirement extraction followed by deterministic code comparison. Current demo-data evaluations are documented in [Compliance evaluation](docs/COMPLIANCE_EVAL.md):

- the tuned 17-case GFZ set reached 94% overall accuracy with 0% false positives before the final ground-truth correction;
- an independent 15-case Lindenhof holdout reached 91% overall accuracy, 19% false-negative rate, and 0% false-positive rate;
- the expanded 23-case nomenclature set reached 84% overall accuracy with Q4_K_M and 90% with Q8_0;
- Magistral Small 24B Q4_K_M with reasoning disabled showed a worse false-negative rate than both NeMo variants in the same 23-case comparison.

These are small, partly synthetic evaluation sets used for engineering decisions—not customer-facing accuracy guarantees. Validation on a real customer IFC model and its actual compliance documents remains required before making external performance claims.

> **Safety position:** Doctus assists a qualified reviewer; it does not replace a fire-protection engineer, acoustic consultant, architect, or other responsible professional. A missing alert does not prove compliance.

## Architecture

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React 18, Tailwind CSS, Monaco Editor, Three.js, Framer Motion |
| Backend API | FastAPI, SQLAlchemy, Alembic |
| Background processing | Celery |
| Queue/cache | Valkey 8, Redis wire-compatible |
| Database | PostgreSQL with pgvector |
| Local AI | Ollama, BGE-M3; optional Mistral NeMo Q4_K_M on delivery hardware |
| AEC/document parsing | IfcOpenShell, ezdxf, pypdf, Tesseract OCR |
| Authentication | OIDC-compatible identity providers |

The default Compose stack contains:

- `db` — PostgreSQL/pgvector,
- `redis` — Valkey,
- `ollama` — local model runtime,
- `backend-api` — FastAPI application,
- `parser-worker` — Celery ingestion and analysis worker,
- `parser-beat` — scheduled connector sync,
- `frontend` — Next.js application.

## Getting started

### Requirements

- Linux host (Ubuntu/Debian recommended)
- Docker Engine with Docker Compose V2
- sufficient disk space for images, model weights, indexed documents, and repositories
- an OIDC provider for real deployments

GPU acceleration is optional and used automatically by Ollama when available. Hardware sizing depends on model, context length, concurrency, and project size; consult [Deployment](docs/DEPLOYMENT.md) before customer installation.

### Online installation

```bash
git clone --branch main --single-branch https://github.com/MaxDedecke/Doctus.git
cd Doctus
./install.sh
```

The installer:

1. checks Docker and Compose,
2. creates missing secrets and `.env` values,
3. builds and starts the stack,
4. runs Alembic migrations,
5. pulls BGE-M3; an explicit non-`disabled` `LLM_MODEL` additionally pulls the validated delivery LLM.

Configure the OIDC and externally reachable URLs in `.env`, then apply them with:

```bash
docker compose up -d
```

Do not use `docker compose restart` after changing `.env`; Compose injects environment variables when containers are created.

Default local endpoints:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Ollama: `http://localhost:11434`

A real deployment must terminate TLS in a trusted reverse proxy. See [Deployment](docs/DEPLOYMENT.md) for URL, OIDC, TLS, backup, update, and troubleshooting guidance.

### Air-gapped installation

Build the offline bundle on a connected x86_64 machine:

```bash
./scripts/build-offline-bundle.sh [version]
```

Transfer the resulting `dist/doctus-offline-bundle-<version>/` directory through a customer-approved secure channel and run:

```bash
./install-offline.sh
```

The installer verifies `SHA256SUMS` before loading images and models. Detailed instructions are in [Deployment](docs/DEPLOYMENT.md) and [Customer deployment](docs/deployment-customer.md).

## Repository structure

```text
frontend/        Next.js workspace and UI components
backend/         FastAPI API, authentication, RAG, agents, and database migrations
parser/          Celery workers, connectors, parsers, embeddings, and compliance tasks
config/          Runtime feature configuration
scripts/         Installers, offline bundle tooling, diagnostics, seed and eval scripts
docs/            Architecture, security, compliance, deployment, and product documentation
data/            Local persistent PostgreSQL, Ollama, and log data (runtime)
repos/           Indexed checkouts and uploaded project files (runtime)
```

Important entry points:

- [frontend/app/page.tsx](frontend/app/page.tsx) — workspace orchestration
- [frontend/components/ChatView.tsx](frontend/components/ChatView.tsx) — chat and model profile UI
- [frontend/components/BimCadViewer.tsx](frontend/components/BimCadViewer.tsx) — BIM/CAD and compliance UI
- [backend/api/chat.py](backend/api/chat.py) — chat/RAG API
- [backend/core/config.py](backend/core/config.py) — backend model and provider configuration
- [parser/tasks/compliance.py](parser/tasks/compliance.py) — compliance retrieval, extraction, and comparison
- [parser/core/config.py](parser/core/config.py) — worker model configuration
- [docker-compose.yml](docker-compose.yml) — online deployment stack

## Security and data handling

Doctus is designed for single-tenant, self-hosted environments:

- cloud LLM providers are opt-in and fail closed when disabled,
- tokens and stored content use application-level encryption,
- OIDC provides authentication,
- access is restricted by team and project,
- customer documents are excluded from the diagnostics bundle,
- offline bundles include integrity checks,
- service images are pinned by digest where applicable.

Local deployment reduces external data transfer but does not by itself establish GDPR, NDA, or regulatory compliance. Operators remain responsible for configuration, lawful processing, retention, access policies, backups, TLS, identity-provider security, and customer-specific agreements. See:

- [Diagnostics hardening](docs/DIAGNOSTICS_HARDENING.md)
- [Prompt injection from external sources](docs/PROMPT_INJECTION.md)
- [AVV template](docs/AVV_VORLAGE.md)
- [Data-flow overview](docs/DATENFLUSS_UEBERSICHT.md)
- [Open-source clearing](docs/OPEN_SOURCE_CLEARING.md)

## Development and pilot status

The technical core is implemented and the repository is being prepared for its first controlled customer pilot. Remaining release gates include:

- confidence/uncertainty labeling for compliance alerts,
- evaluation against real customer data,
- final customer-facing IFC export requirements,
- final advisory-only language and contractual review,
- customer-specific AVV/data-flow documentation.

See [Pilot roadmap](ROADMAP_PILOTKUNDE.md) for the current work plan.

## License

Doctus's source code is proprietary and not open source. All rights are reserved.

The product includes third-party software under permissive and copyleft licenses and local AI models under their respective model licenses. Distribution obligations and the current dependency/model audit are documented in [Open-source clearing](docs/OPEN_SOURCE_CLEARING.md).
