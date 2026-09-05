"""O-072: process_knowledge_source/process_local_document müssen die
trace_id des auslösenden Backend-Requests für die Dauer des Sync-Laufs
setzen — analog zu compute_entity_links/compute_knowledge_links/
generate_diagnostics_bundle, die core.tracing.trace_id_scope() bereits
nutzen. Ohne das ließ sich ein Kundenbericht "meine Quelle hat nicht
synchronisiert" nicht mit dem ursprünglichen, getracten API-Request
verknüpfen.

Bewusst keine @pytest.mark.anyio-Tests: die Celery-Tasks rufen intern
asyncio.run() auf (wie im echten Worker-Prozess auch), was innerhalb
eines bereits laufenden Event-Loops fehlschlägt."""

import worker
from core.tracing import get_trace_id


def test_process_knowledge_source_task_applies_trace_id_scope(monkeypatch):
    seen = {}

    async def fake_async(source_id, force_reindex=False):
        seen["trace_id"] = get_trace_id()
        seen["force_reindex"] = force_reindex

    monkeypatch.setattr(worker, "process_knowledge_source_async", fake_async)
    monkeypatch.setattr(worker, "_register_task_id", lambda *a, **k: None)

    worker.process_knowledge_source(source_id=1, force_reindex=True, trace_id="trace-xyz")

    assert seen == {"trace_id": "trace-xyz", "force_reindex": True}
    # trace_id_scope muss nach dem Task-Lauf wieder zurückgesetzt sein.
    assert get_trace_id() == "-"


def test_process_knowledge_source_task_defaults_to_dash_without_trace_id(monkeypatch):
    """Beat-getriggerte Syncs (scan_pull_sources) übergeben keine trace_id --
    das darf nicht crashen, sondern muss den bestehenden "-"-Platzhalter
    verwenden."""
    seen = {}

    async def fake_async(source_id, force_reindex=False):
        seen["trace_id"] = get_trace_id()

    monkeypatch.setattr(worker, "process_knowledge_source_async", fake_async)
    monkeypatch.setattr(worker, "_register_task_id", lambda *a, **k: None)

    worker.process_knowledge_source(source_id=1)

    assert seen["trace_id"] == "-"


def test_process_local_document_task_applies_trace_id_scope(monkeypatch):
    seen = {}

    async def fake_async(source_id, file_path):
        seen["trace_id"] = get_trace_id()
        seen["file_path"] = file_path

    monkeypatch.setattr(worker, "process_local_document_async", fake_async)
    monkeypatch.setattr(worker, "_register_task_id", lambda *a, **k: None)

    worker.process_local_document(source_id=1, file_path="/uploads/x.pdf", trace_id="trace-abc")

    assert seen == {"trace_id": "trace-abc", "file_path": "/uploads/x.pdf"}
