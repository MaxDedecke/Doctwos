"""Visible diagnostics for bounded per-routine data-flow extraction."""

from core.model import ParseDiagnostic


def flow_limit_diagnostic(entities):
    limited = [entity for entity in entities if entity.meta.get("data_flow_truncated")]
    if not limited:
        return None
    return ParseDiagnostic(
        code="JAVA_DATA_FLOW_TRUNCATED",
        severity="warning",
        phase="parser",
        message=f"Datenfluss in {len(limited)} Routine(n)/Initialisierungsbereichen auf 80 Anweisungen begrenzt; spätere Zuweisungen sind nicht vollständig erfasst.",
        line=limited[0].start_line,
        column=0,
        count=len(limited),
    )
