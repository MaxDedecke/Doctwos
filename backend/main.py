"""
backend/main.py
================
App-Factory für den Doctus AI Backend Service.

Diese Datei hat nur eine Aufgabe: FastAPI konfigurieren und die Router einbinden.
Alle Endpoint-Logik liegt in backend/api/ — je eine Datei pro Ressource:

    api/chat.py            — Chat mit SSE-Streaming und Session-Management
    api/knowledge_sources.py — Wissensquellen (Git, Confluence, Jira, WebDAV, Upload)
    api/connectors.py      — Verbindungstest für Git- und Wissensquellen-Connectoren
    api/entity_links.py    — Link Manager (Code-Entity ↔ Wissens-Dokument)
    api/system.py          — Health-Check, LLM-Modell-Verwaltung
    api/auth.py            — Lokale Anmeldung (Benutzername/Passwort)

Konfiguration (URLs, Modellnamen, Redis):
    backend/core/config.py

Datenbank-Schemata (ORM):
    backend/models/database.py

Schema-Migrationen (Alembic, alembic upgrade head läuft vor App-Start im
Docker-Entrypoint — siehe backend/docker-entrypoint.sh):
    backend/alembic/

Auth:
    Alle Router außer system und auth verlangen eine gültige Session
    (core/auth_dependency.py::get_current_user). system bleibt offen für
    Healthchecks der Container-Orchestrierung; auth ist der Login-Flow selbst.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import core.config as cfg
from core.tracing import TraceIdFilter, trace_id_middleware

_log_format = "%(asctime)s %(levelname)s %(name)s [%(trace_id)s]: %(message)s"
_handlers: list[logging.Handler] = [logging.StreamHandler()]

# Additive file handler onto the shared /var/log/doctus mount (see
# docker-compose.yml) — lets the diagnostics-bundle Celery task read this
# service's logs directly, no Docker socket needed. Falls back to stdout-only
# when the path isn't writable (e.g. local dev outside Docker).
_log_file_path = os.getenv("LOG_FILE_PATH")
if _log_file_path:
    try:
        os.makedirs(os.path.dirname(_log_file_path), exist_ok=True)
        _handlers.append(logging.FileHandler(_log_file_path))
    except OSError:
        pass

logging.basicConfig(level=cfg.LOG_LEVEL, format=_log_format, handlers=_handlers)
# basicConfig() only wires the filter's own logger; every *other* logger's
# records reach this handler via propagation, so the filter has to live on
# the handler itself to see them all.
for _handler in logging.getLogger().handlers:
    _handler.addFilter(TraceIdFilter())

from api import (
    auth,
    chat,
    knowledge_sources,
    connectors,
    entity_links,
    system,
    knowledge_links,
    topics,
    graph,
    search,
    teams,
    users,
    projects,
    diagnostics,
    entities,
    callgraph,
    process,
    change_packages,
    jobs,
    audit,
    feedback_diagnostics,
    insights,
    mcp_tokens,
)
from api.config_router import router as config_router
from core.auth_dependency import get_current_user
from core.db_setup import SessionLocal, bootstrap_superuser
from services.ai_settings import initialize_runtime_settings
from core.teams import require_admin
from mcp_server import asgi_app as inbound_mcp_app, mcp as inbound_mcp

@asynccontextmanager
async def _lifespan(app: FastAPI):
    bootstrap_superuser()
    initialize_runtime_settings(SessionLocal)
    async with inbound_mcp.session_manager.run():
        yield


app = FastAPI(title="Doctus AI Backend", lifespan=_lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[cfg.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # O-073: Frontend und Backend sind verschiedene Origins; ein Browser gibt
    # dem JavaScript aus einer Cross-Origin-Antwort NUR die sechs
    # CORS-safelisted Response-Header heraus. Ohne diese Zeile kann das
    # Frontend das unten gesetzte X-Request-ID nicht lesen -- kein Fehler,
    # kein Log, der Header ist schlicht unsichtbar.
    expose_headers=["X-Request-ID"],
)

# Reads/generates X-Request-ID so every log line for this request (and, where
# explicitly threaded through into a Celery send_task call, the resulting
# parser-worker task) can be correlated. Registered last so it wraps innermost
# and sees the request before CORS/Session touch it.
app.middleware("http")(trace_id_middleware)

_authenticated = [Depends(get_current_user)]

app.include_router(system.router)
app.include_router(config_router)
app.include_router(auth.router)
app.include_router(projects.router, dependencies=_authenticated)
app.include_router(chat.router, dependencies=_authenticated)
app.include_router(knowledge_sources.router, dependencies=_authenticated)
app.include_router(connectors.router, dependencies=_authenticated)
app.include_router(entity_links.router, dependencies=_authenticated)
app.include_router(knowledge_links.router, dependencies=_authenticated)
app.include_router(topics.router, dependencies=[Depends(require_admin)])
app.include_router(diagnostics.router, dependencies=[Depends(require_admin)])
# Unauthenticated on purpose — see public_router's docstring in api/diagnostics.py.
app.include_router(diagnostics.public_router)
app.include_router(graph.router, dependencies=_authenticated)
app.include_router(search.router, dependencies=_authenticated)
app.include_router(entities.router, dependencies=_authenticated)
app.include_router(callgraph.router, dependencies=_authenticated)
app.include_router(process.router, dependencies=_authenticated)
app.include_router(change_packages.router, dependencies=_authenticated)
app.include_router(jobs.router, dependencies=_authenticated)
app.include_router(audit.router, dependencies=[Depends(require_admin)])
app.include_router(feedback_diagnostics.router, dependencies=[Depends(require_admin)])
app.include_router(insights.router, dependencies=_authenticated)
app.include_router(teams.router)
app.include_router(users.router)
app.include_router(mcp_tokens.router, dependencies=_authenticated)
# The SDK handles the exact /mcp route. A root mount avoids Starlette's
# /mcp -> /mcp/ redirect while ordinary FastAPI routes keep precedence.
app.mount("/", inbound_mcp_app)
