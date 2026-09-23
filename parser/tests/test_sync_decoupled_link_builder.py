"""Tests for O-315: Decouple automatic link builder from source sync."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from tasks import sync
from models.database import KnowledgeSource, LinkBuilderRun


@pytest.mark.anyio
async def test_process_knowledge_source_does_not_auto_trigger_entity_links(monkeypatch):
    """
    O-315: After a successful source sync with changes, no LinkBuilderRun
    or compute_entity_links task must be created or sent to Celery.
    Link building requires an explicit user action.
    """
    fake_source = KnowledgeSource(
        id=101,
        type="git",
        project_id=42,
        sync_status="syncing",
    )

    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = fake_source

    monkeypatch.setattr(sync, "SessionLocal", lambda: fake_db)

    fake_connector = MagicMock()
    fake_connector.has_changes = True
    fake_connector.sync = AsyncMock()

    monkeypatch.setattr(sync, "get_connector", lambda source_type: lambda source_id: fake_connector)

    sent_tasks = []
    fake_celery = MagicMock()
    fake_celery.send_task.side_effect = lambda name, *a, **k: sent_tasks.append((name, a, k))
    monkeypatch.setattr("celery.current_app", fake_celery)

    await sync.process_knowledge_source_async(101)

    fake_connector.sync.assert_awaited_once()

    # Ensure no LinkBuilderRun was added to DB
    for call in fake_db.add.call_args_list:
        obj = call[0][0]
        assert not isinstance(obj, LinkBuilderRun), "LinkBuilderRun must not be created on sync (O-315)"

    # Ensure no Celery task was sent
    assert len(sent_tasks) == 0, "compute_entity_links task must not be sent on sync (O-315)"
