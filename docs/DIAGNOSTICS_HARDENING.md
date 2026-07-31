# Diagnostics & Observability Hardening

Findings from a 2026-07 diagnosis session that surfaced three separate bugs
in one sitting, all with the same shape: an error gets caught, logged
minimally (or not at all), and the code silently falls back to behavior that
looks like success from the outside. This doc tracks what needs to change so
the next occurrence of that pattern is visible from the DB/logs instead of
requiring someone at the keyboard to notice it live.

## Original gaps (2026-07 diagnosis session) — status

The four gaps below are what motivated this doc. Three of the four are now
**Done** (see Priority section for the fixes); kept here as the "why", not as
an open-items list — don't read this section as still-current status.

**Error persistence was inconsistent across task types.**
- `ComplianceRun` (`backend/models/database.py:342`) was (and remains) the
  model to copy: `status` (`pending/running/completed/failed`) +
  `error_message` (`Text`, not just a short string) +
  `progress`/`progress_message`, so a run that crashed is distinguishable
  from one that legitimately found nothing.
- `KnowledgeSource.last_error`/`sync_log` follow the same *shape* but only
  store a string, never a traceback (still true, not addressed by the
  `LinkBuilderRun` work below — a smaller, accepted gap).
- The four AEC connectors (IFC/DWG/GAEB/Folder) had per-file error handling
  that was inconsistent about where it went — some reached `sync_log`, some
  was a bare `print()` that only existed in container stdout. **Done:** all
  `print()` calls converted to `logger.*` (Priority item 8).
- `compute_entity_links`/`compute_knowledge_links` had no persistent error
  state at all — a crash only produced a `logger.error(...)` line in
  container-scoped logs, no status column, no run history. **Done:** the new
  `LinkBuilderRun` table closes this (Priority item 3).
- **Still open:** `backend/agent.py`'s tool calls (`list_repo_files`,
  `view_repo_file`, etc.) still catch exceptions and return
  `{"error": str(e)}` to the LLM only — never logged server-side, so a tool
  failure during a customer chat remains invisible to us even in the logs.
  Not covered by any Priority item yet.

**No readiness check — "Up" didn't mean "working".** **Done** (Priority item
4): `GET /health` now pings DB/Redis/Ollama and returns 503 with per-check
detail on failure; every service in `docker-compose.yml`/
`docker-compose.offline.yml` has a `healthcheck:` block.

**Frontend errors were completely invisible to us.** **Done** (Priority item
7): `frontend/app/error.tsx` and `frontend/app/global-error.tsx` now exist,
with an opt-in "send error report" button posting to
`POST /diagnostics/client-error`.

**Data sensitivity, in case a customer is asked for "the whole DB".**
- `DocumentChunk.content` (actual customer documents/BIM data),
  `ChatMessage.content`, and `User.email` are stored unencrypted.
- `Repository.token`/`KnowledgeSource.token` (Git/Confluence/Jira
  credentials) are encrypted via `MASTER_ENCRYPTION_KEY` — but
  `MASTER_ENCRYPTION_KEY` + a Postgres dump together fully decrypt them
  (already documented in `docs/DEPLOYMENT.md`).
- `scripts/generate_diagnostics.py` already deliberately excludes
  `DocumentChunk`/`ChatMessage` and redacts `.env` secrets — the instinct is
  right, but redaction is currently string-match based (see coverage gaps
  below) rather than schema-aware.

## Priority

### High leverage, low effort (hours)
1. ~~Finish and wire up `scripts/generate_diagnostics.py`~~ **Done:** now
   also collects frontend container logs, `compliance_runs` rows, the
   applied Alembic revision, and `docker-compose` image IDs; linked from
   `docs/DEPLOYMENT.md` and `docs/deployment-customer.md`.
2. ~~Document explicitly that a restart/redeploy destroys the logs
   irrecoverably~~ **Done:** onboarding note in
   `docs/deployment-customer.md` — capture the diagnostics bundle before
   any restart/redeploy.

### High leverage, medium effort (1-2 days)
3. ~~Give `compute_entity_links`/`compute_knowledge_links` the same
   status/error-persistence mechanism `ComplianceRun` already has~~ **Done:**
   new `LinkBuilderRun` table (status/progress_message/error_message/
   links_created/finished_at), created by every caller (API triggers,
   post-sync auto-recompute, pending-flag requeue) and updated by the tasks
   themselves; `GET /projects/{id}/link-builder-runs` and
   `GET /knowledge-links/runs` expose history.
4. ~~Turn `/health` into a real readiness check~~ **Done:** `/health` now
   pings DB (`SELECT 1`), Redis (`PING`), and Ollama (`/api/tags`), returns
   503 + per-check detail on any failure. `healthcheck:` blocks added to
   every service in `docker-compose.yml` and `docker-compose.offline.yml`
   (db: `pg_isready`, redis: `redis-cli ping`, ollama: TCP connect since the
   image has no curl, backend: hits `/health`, parser-worker: `celery
   inspect ping`, parser-beat: `parser/healthcheck_beat.py` process check
   since beat doesn't answer broadcast pings, frontend: Node `http.get`).
5. ~~Add a `/version` endpoint returning git SHA + build time~~ **Done:**
   `GET /version` reads `GIT_SHA`/`BUILD_TIME` env vars baked in by
   `backend/Dockerfile` `ARG`s; `docker-compose.yml` passes them as build
   args (empty locally → "unknown"), `scripts/build-offline-bundle.sh` sets
   them from `DOCTUS_VERSION`/`date -u` for shipped builds.

### Was "can wait until after the first PoC" — now done (2026-07-06)
6. ~~Request/trace-ID middleware spanning backend + parser~~ **Done:**
   `backend/core/tracing.py` (contextvar + logging filter + HTTP middleware)
   generates/reads `X-Request-ID`, injects it into every backend log line, and
   is threaded explicitly into `send_task(...)` calls for request-originated
   Celery tasks (entity/knowledge links, compliance check, the new
   diagnostics bundle below) via a `trace_id` kwarg — Celery doesn't carry
   HTTP headers across the process boundary, so this can't be automatic.
   `parser/core/tracing.py` is the Celery-side counterpart (a
   `trace_id_scope` context manager instead of a middleware). Note:
   `app.conf.worker_hijack_root_logger = False` had to be set in
   `parser/worker.py` — Celery overrides the root logger at startup by
   default, which silently discarded our format/handlers otherwise.
7. ~~A frontend error boundary with an optional, opt-in "send error report"
   button~~ **Done:** `frontend/app/error.tsx` (segment-level, has i18n) and
   `frontend/app/global-error.tsx` (root-layout crashes only — renders its own
   `<html>/<body>`, so no `LanguageProvider` context is available, hence
   hardcoded English). Both POST to `POST /diagnostics/client-error`
   (deliberately unauthenticated — a crash can happen before login) only when
   the user clicks the button, never automatically.
8. ~~Logging consistency: replace parser-worker `print()` calls with
   `logger`, standardize on one `basicConfig` setup~~ **Done:** all `print()`
   calls in `parser/utils.py` and `parser/connectors/{base,dwg,folder,notion,
   ifc,gaeb}.py` converted to `logger.info`/`logger.error`; `parser/worker.py`
   now calls `logging.basicConfig` (previously relied on Celery's default).

### New since the PoC: admin-triggered diagnostics bundle (2026-07-06)
Beyond the three deferred items above, a `DiagnosticsRun` model (mirrors
`LinkBuilderRun`'s pending/running/completed/failed shape) plus a Celery task
(`parser/tasks/diagnostics.py`) let an admin generate a diagnostics bundle
from Settings → Logs without shell access — `POST /diagnostics/generate`,
`GET /diagnostics/runs`, `GET /diagnostics/runs/{id}/download`
(`backend/api/diagnostics.py`, admin-gated via `require_admin`).

This is a **reduced** bundle compared to `scripts/generate_diagnostics.py`,
by design: the task runs inside `parser-worker`, which has no Docker
socket/CLI, so it cannot shell out to `docker compose exec`/`docker compose
logs` the way the script does. Instead:
- DB metadata is queried directly via SQLAlchemy (not `psql` via `docker exec`).
- Service logs are read directly off a new shared bind mount
  (`./data/logs/<service>` per service in `docker-compose.yml`/
  `docker-compose.offline.yml`, mounted as the whole tree into `parser-worker`
  read/write so the task can see every service's own log file). Each
  service's logging setup gained an additive `FileHandler` (`LOG_FILE_PATH`
  env var) alongside its existing stdout/json-file logging; the frontend
  (`next start`, no Python logging) instead has its stdout `tee`'d to the
  same mount via its `docker-compose.yml` `command:`.
- Docker container status, image digests, and `ollama list` are **not**
  included — those still require `scripts/generate_diagnostics.py` run
  manually on the host with Docker CLI access.

The bundle tarball is written under `./repos/diagnostics/` — the existing
`./repos` bind mount already shared between `backend-api` and `parser-worker`,
so the backend can serve the download without any new shared path.
