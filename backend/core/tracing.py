"""
backend/core/tracing.py
========================
Request-Trace-ID: verbindet einen HTTP-Request mit allen Log-Zeilen, die
während seiner Bearbeitung entstehen (inkl. eines später ausgelösten
Celery-Tasks, dem die ID explizit als Argument mitgegeben wird — Celery trägt
HTTP-Header nicht automatisch über die Prozessgrenze).

Ohne dieses Modul lässt sich ein Fehler, der in mehreren Log-Zeilen über
mehrere Services verteilt auftaucht, nur über Zeitstempel und Zuruf
zusammensetzen.
"""

import contextvars
import logging
import uuid

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id_var.reset(token)


class TraceIdFilter(logging.Filter):
    """Injiziert %(trace_id)s in jeden LogRecord, auch für Logger, die außerhalb
    eines Requests laufen (Startup-Code, Celery) — dort bleibt es der Default "-"."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


async def trace_id_middleware(request, call_next):
    incoming = request.headers.get("x-request-id")
    trace_id = incoming if incoming else uuid.uuid4().hex
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
    finally:
        reset_trace_id(token)
    response.headers["X-Request-ID"] = trace_id
    return response
