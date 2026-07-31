"""
parser/core/tracing.py
=======================
Trace-ID-Gegenstück zu backend/core/tracing.py. Celery trägt HTTP-Header nicht
über die Prozessgrenze — die ID kommt hier explizit als Task-Kwarg an
(trace_id=...) und wird für die Dauer des Tasks in einer ContextVar gehalten,
damit alle Log-Zeilen dieses Task-Laufs dieselbe ID tragen wie der ursprüngliche
Backend-Request.

Datei bewusst dupliziert statt importiert: backend/ und parser/ sind getrennte
Docker-Images ohne gemeinsames Package (siehe die bereits bestehende Duplizierung
von models/database.py).
"""

import contextvars
import logging

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return _trace_id_var.get()


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


class trace_id_scope:
    """Context manager: sets the trace ID for a Celery task's duration.

    Usage: with trace_id_scope(trace_id or "-"): ...task body...
    """

    def __init__(self, trace_id: str | None):
        self._trace_id = trace_id or "-"
        self._token = None

    def __enter__(self):
        self._token = _trace_id_var.set(self._trace_id)
        return self

    def __exit__(self, exc_type, exc, tb):
        _trace_id_var.reset(self._token)
        return False
