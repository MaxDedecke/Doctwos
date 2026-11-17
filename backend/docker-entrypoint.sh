#!/bin/sh
set -e

alembic upgrade head

if [ "$UVICORN_RELOAD" = "1" ]; then
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
fi
# MCP-Clients (IDE-Agenten) senden ihre nächste Anfrage oft nach mehreren Sekunden Modellzeit über dieselbe
# Verbindung. Mit uvicorns Standard von 5 s schließt der Server sie genau dann, und der Client bekommt
# "Server disconnected without sending a response" (Benchmark 17.11.: Abbruch nach 23 Sitzungen).
exec uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive "${UVICORN_KEEPALIVE_SECONDS:-75}"
