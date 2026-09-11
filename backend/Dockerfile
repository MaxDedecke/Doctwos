FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93 AS builder

WORKDIR /app

# Build tools only exist in this stage (O-167): psycopg2-binary ships its own
# libpq, but other deps may fall back to a source build on platforms without a
# matching manylinux wheel. Neither build-essential nor libpq-dev end up in
# the runtime image below.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# vendor/ vor dem pip install kopieren: requirements.txt referenziert
# ./vendor/unidecode_shim als lokalen Ersatz fuer die GPL-Transitivabhaengigkeit
# von mcp-atlassian (siehe docs/ENTSCHEIDUNGEN.md E-7). Landet ueber pip als
# installiertes Paket in /root/.local, der Ordner selbst muss nicht in die
# Runtime-Stage.
COPY vendor/ vendor/
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# Keine Node.js-Runtime im Backend-Image (F-049): der einzige Node-Bedarf war der
# Notion-MCP-Server, und Notion ist mit dem Doctus-Fork entfallen. mcp-atlassian
# (Jira/Confluence) ist reines Python über requirements.txt.

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Nur der fuer den Betrieb noetige Code (O-167): keine tests/, kein
# requirements-dev.txt, kein vendor/-Quellbaum, keine Build-Werkzeuge. Wer
# `docker exec`/`docker save` gegen dieses Image faehrt, sieht die
# Anwendungslogik weiterhin (Python ist interpretiert und muss als Quelltext
# vorliegen, um zu laufen) - aber nicht mehr Tests, Dev-Tooling oder die
# Build-Kette obendrein.
COPY api/ api/
COPY core/ core/
COPY models/ models/
COPY services/ services/
COPY alembic/ alembic/
COPY alembic.ini .
COPY main.py agent.py mcp_client.py ./
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Baked in at build time so GET /version can report what's actually running
# without relying on a bind-mounted .git dir (there isn't one in production).
ARG GIT_SHA=unknown
ARG BUILD_TIME=unknown
ENV GIT_SHA=$GIT_SHA
ENV BUILD_TIME=$BUILD_TIME

ENTRYPOINT ["./docker-entrypoint.sh"]
