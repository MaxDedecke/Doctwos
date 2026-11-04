"""Vorschläge, deren Abschnitt ein Re-Index entfernt hat, bewertet der nächste Link-Lauf gegen die aktuellen Abschnitte neu."""

import uuid

import pytest
from sqlalchemy import text

import tasks.link_builder as link_builder
from chunk_reindex import STALE_NOTE
from db import SessionLocal
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeSource,
    LinkBuilderRun,
)


@pytest.fixture
def workspace():
    db = SessionLocal()
    team_id = db.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:n, now()) RETURNING id"),
        {"n": f"orphan-{uuid.uuid4().hex[:8]}"},
    ).scalar_one()
    project_id = db.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES ('orphan', :t, now()) RETURNING id"
        ),
        {"t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="handbuch", type="Local", team_id=team_id, project_id=project_id)
    db.add(source)
    db.flush()
    entity = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="PAYCALC.cbl",
        name="PAYCALC",
        type="program",
    )
    chunk = DocumentChunk(
        project_id=project_id,
        source_id=source.id,
        file_path="handbuch.md",
        content="PAYCALC berechnet die monatlichen Gehälter.",
        start_line=1,
        end_line=1,
        metadata_json={"language": "markdown", "title": "Handbuch", "source_type": "Local"},
    )
    db.add_all([entity, chunk])
    db.flush()
    orphan = EntityDocLink(
        project_id=project_id,
        entity_id=entity.id,
        chunk_id=None,
        doc_title="Handbuch",
        source_type="Local",
        link_type="keyword",
        status="pending",
        created_by="auto",
        context=STALE_NOTE + "Der frühere Abschnitt nannte PAYCALC.",
    )
    # Ein früherer, abgeschlossener Lauf: Ohne Queue-Einträge wäre dieser Lauf sonst leer.
    db.add_all(
        [
            orphan,
            LinkBuilderRun(project_id=project_id, task_type="entity_links", status="completed"),
        ]
    )
    run = LinkBuilderRun(project_id=project_id, task_type="entity_links", status="pending")
    db.add(run)
    db.commit()
    try:
        yield db, project_id, entity, chunk, orphan.id, run.id
    finally:
        db.rollback()
        db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id).delete()
        db.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == project_id).delete()
        db.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).delete()
        db.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
        db.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        db.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        db.commit()
        db.close()


@pytest.mark.anyio
async def test_next_run_reviews_the_entity_of_an_orphaned_suggestion_and_replaces_it(
    workspace, monkeypatch
):
    db, project_id, entity, chunk, orphan_id, run_id = workspace

    async def nothing(*args, **kwargs):
        return {}

    async def review(prompt, model, **kwargs):
        return {
            "index": 0,
            "confidence": 90,
            "section": "Das Handbuch nennt `PAYCALC` als Programm für die Gehälter.",
            "code": "Das Programm `PAYCALC` ist die bewertete Entity.",
            "uncertain": "Einzelheiten der Berechnung nennt der Abschnitt nicht.",
        }

    async def no_pull(model):
        return None

    monkeypatch.setattr(link_builder, "_embed_context_window", nothing)
    monkeypatch.setattr(link_builder, "_pass_semantic", nothing)
    monkeypatch.setattr(link_builder, "get_chat_json", review)
    monkeypatch.setattr(link_builder, "ensure_model_pulled", no_pull)
    assert link_builder._orphaned_entity_ids(db, project_id) == {entity.id}

    await link_builder.compute_entity_links_async(run_id, project_id)

    db.expire_all()
    assert db.get(LinkBuilderRun, run_id).status == "completed"
    links = db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id).all()
    assert [(link.chunk_id, link.status) for link in links] == [(chunk.id, "pending")]
    assert links[0].id != orphan_id
    assert links[0].context.startswith("Im Abschnitt: Das Handbuch nennt `PAYCALC`")
    assert link_builder._orphaned_entity_ids(db, project_id) == set()
