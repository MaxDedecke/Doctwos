"""Eingeschränkter Link-Lauf: nur Code-Entitäten gewählter Typen gegen Dokumentation gewählter Quellen."""

import uuid

import pytest
from sqlalchemy import text

import tasks.link_builder as link_builder
from db import SessionLocal
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeSource,
    LinkBuilderDirtyItem,
    LinkBuilderRun,
)
from tasks.link_run_scope import LinkRunScope, select_run_entities


def test_scope_reads_types_and_sources_and_ignores_junk():
    scope = LinkRunScope.from_scope(
        {"filter": {"entity_types": ["program", " section ", ""], "doc_source_ids": [3, "4", "x"]}}
    )
    assert scope.entity_types == {"program", "section"}
    assert scope.doc_source_ids == {3, 4}
    assert scope.targeted
    assert not LinkRunScope.from_scope({"filter": "kaputt"}).targeted
    assert not LinkRunScope.from_scope(None).targeted


@pytest.fixture
def workspace():
    db = SessionLocal()
    team_id = db.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:n, now()) RETURNING id"),
        {"n": f"scope-{uuid.uuid4().hex[:8]}"},
    ).scalar_one()
    project_id = db.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES ('scope', :t, now()) RETURNING id"
        ),
        {"t": team_id},
    ).scalar_one()
    handbook = KnowledgeSource(
        name="handbuch", type="Local", team_id=team_id, project_id=project_id
    )
    tickets = KnowledgeSource(name="tickets", type="Jira", team_id=team_id, project_id=project_id)
    db.add_all([handbook, tickets])
    db.flush()
    entities = {
        kind: CodeEntity(
            project_id=project_id, file_path="PAYCALC.cbl", name=name, type=kind, start_line=1
        )
        for kind, name in (
            ("program", "PAYCALC"),
            ("section", "MAIN-SECTION"),
            ("paragraph", "INIT-PARA"),
        )
    }
    text_body = "PAYCALC mit MAIN-SECTION und INIT-PARA berechnet die Gehälter."
    chunks = {
        source.name: DocumentChunk(
            project_id=project_id,
            source_id=source.id,
            file_path=f"{source.name}.md",
            content=text_body,
            start_line=1,
            end_line=1,
            metadata_json={
                "language": "markdown",
                "title": source.name,
                "source_type": source.type,
            },
        )
        for source in (handbook, tickets)
    }
    db.add_all([*entities.values(), *chunks.values()])
    db.flush()
    dirty = LinkBuilderDirtyItem(
        project_id=project_id, entity_id=entities["paragraph"].id, status="pending"
    )
    run = LinkBuilderRun(
        project_id=project_id,
        task_type="entity_links",
        status="pending",
        scope_json={
            "project_id": project_id,
            "filter": {"entity_types": ["program", "section"], "doc_source_ids": [handbook.id]},
        },
    )
    db.add_all([dirty, run])
    db.commit()
    try:
        yield db, project_id, entities, chunks, run.id, dirty.id
    finally:
        db.rollback()
        db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id).delete()
        db.query(LinkBuilderDirtyItem).filter(
            LinkBuilderDirtyItem.project_id == project_id
        ).delete()
        db.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == project_id).delete()
        db.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).delete()
        db.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
        db.query(KnowledgeSource).filter(KnowledgeSource.project_id == project_id).delete()
        db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
        db.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        db.commit()
        db.close()


@pytest.mark.anyio
async def test_targeted_run_links_only_chosen_types_to_chosen_sources(workspace, monkeypatch):
    db, project_id, entities, chunks, run_id, dirty_id = workspace

    async def nothing(*args, **kwargs):
        return {}

    async def review(prompt, model, **kwargs):
        return {
            "index": 0,
            "confidence": 90,
            "section": "Der Abschnitt nennt `PAYCALC` und seine Teile.",
            "code": "Die bewertete Entity gehört zu `PAYCALC`.",
            "uncertain": "Einzelheiten nennt der Abschnitt nicht.",
        }

    async def no_pull(model):
        return None

    monkeypatch.setattr(link_builder, "_embed_context_window", nothing)
    monkeypatch.setattr(link_builder, "_pass_semantic", nothing)
    monkeypatch.setattr(link_builder, "get_chat_json", review)
    monkeypatch.setattr(link_builder, "ensure_model_pulled", no_pull)

    await link_builder.compute_entity_links_async(run_id, project_id)

    db.expire_all()
    assert db.get(LinkBuilderRun, run_id).status == "completed"
    linked = {
        (link.entity_id, link.chunk_id)
        for link in db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id)
    }
    handbook_chunk = chunks["handbuch"].id
    assert linked == {
        (entities["program"].id, handbook_chunk),
        (entities["section"].id, handbook_chunk),
    }
    # Die Queue gehört den vollständigen Läufen; ein Ausschnitt arbeitet sie nicht ab.
    assert db.get(LinkBuilderDirtyItem, dirty_id) is not None


def test_a_targeted_run_does_not_replace_the_backfill(workspace):
    db, project_id, entities, _chunks, run_id, dirty_id = workspace
    db.query(LinkBuilderDirtyItem).filter(LinkBuilderDirtyItem.id == dirty_id).delete()
    db.get(LinkBuilderRun, run_id).status = "completed"
    db.commit()

    selection = select_run_entities(
        db, project_id, run_id + 1, list(entities.values()), LinkRunScope(), set()
    )

    assert selection.bootstrap
    assert len(selection.entities) == 3
