#!/bin/sh
set -e

alembic upgrade head

if [ "$UVICORN_RELOAD" = "1" ]; then
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
fi
exec uvicorn main:app --host 0.0.0.0 --port 8000
