"""
parser/tasks/sync.py
====================
Generischer Sync-Task für alle Wissensquellen-Typen (Confluence, Notion, Jira, ...).

Dieser Task ersetzt die früheren einzelnen Task-Funktionen process_confluence_source_async,
process_notion_source_async und process_jira_source_async. Statt einer Funktion pro
Connector-Typ gibt es jetzt eine einzige Funktion, die über die ConnectorRegistry den
passenden Connector instanziiert und dessen sync()-Methode aufruft.

Neuen Connector-Typ unterstützen:
    → connectors/registry.py: Eintrag hinzufügen
    Kein Anpassen dieser Datei nötig.
"""

import asyncio
import logging

from connectors.registry import get_connector
from db import SessionLocal
from models.database import KnowledgeSource, LinkBuilderRun

logger = logging.getLogger(__name__)


async def process_knowledge_source_async(source_id: int, force_reindex: bool = False) -> None:
    """
    Instanziiert den passenden Connector für die gegebene KnowledgeSource
    und führt den vollständigen Sync-Ablauf durch.

    Die Connector-Klasse wird anhand des KnowledgeSource.type-Felds aus der
    Registry geladen — dieser Task muss bei neuen Connector-Typen nicht
    geändert werden.

    Args:
        source_id: Primärschlüssel der KnowledgeSource in der DB
        force_reindex: Reparse all Git files even when the commit is unchanged.
    """
    db = SessionLocal()
    source = None
    try:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
        if not source:
            logger.warning(f"[Sync] KnowledgeSource {source_id} nicht gefunden.")
            return
        if source.sync_status == "cancelled":
            logger.info(f"[Sync] KnowledgeSource {source_id} wurde vor dem Start abgebrochen.")
            return
        
        source_type = source.type
        connector_cls = get_connector(source_type)
        connector = connector_cls(source_id)
        if force_reindex and source_type.lower() != "git":
            raise ValueError("Force-Reindex wird nur für Git-Wissensquellen unterstützt.")
        if force_reindex:
            await connector.sync(force_reindex=True)
        else:
            await connector.sync()

        # Semantische Verknüpfungen mit Code-Entities neu berechnen, falls sich Chunks geändert haben
        if source.project_id and getattr(connector, "has_changes", False):
            from celery import current_app as celery_app
            link_run = LinkBuilderRun(task_type="entity_links", project_id=source.project_id, status="pending")
            db.add(link_run)
            db.commit()
            db.refresh(link_run)
            result = celery_app.send_task("compute_entity_links", args=[link_run.id, source.project_id])
            if getattr(result, "id", None):
                link_run.celery_task_id = result.id
                db.commit()
            logger.info(f"[Sync] Link-Berechnung für Projekt {source.project_id} gestartet, da Änderungen vorliegen.")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Sync] Kritischer Fehler für Source {source_id}: {error_msg}")
        
        # Falls der Fehler VOR connector.sync() passiert ist (z.B. get_connector failed),
        # müssen wir hier manuell in die DB loggen, damit der User es im Frontend sieht.
        if source:
            from datetime import datetime, timezone
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            source.sync_status = "error"
            source.last_error = error_msg
            source.sync_log = (source.sync_log or "") + f"[{timestamp}] Initialisierungs-Fehler: {error_msg}\n"
            db.commit()
    finally:
        db.close()
