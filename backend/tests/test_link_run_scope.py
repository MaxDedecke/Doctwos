"""Eingeschränkter Entity-Link-Lauf: Auswahl-Optionen, Prüfung der Auswahl, Schätzung und Start."""

from unittest.mock import patch

import pytest

import api.entity_links as entity_links_api
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeSource,
    LinkBuilderRun,
    Project,
    Team,
)
from services.link_run_scope import language_of_type


def test_types_fall_into_their_language():
    assert language_of_type("program") == "cobol"
    assert language_of_type("section") == "cobol"
    assert language_of_type("copybook") == "cobol"
    assert language_of_type("method") == "java"
    assert language_of_type("compilation_unit") == "java"
    assert language_of_type("jcl_step") == "jcl"
    assert language_of_type("maven_module") == "maven"
    assert language_of_type("something_new") == "other"


@pytest.fixture
def mixed_project(test_project, db_session):
    """COBOL- und Java-Entitäten, Handbuch (Local), Tickets (Jira) und ein Git-Repo mit Code und README."""
    proj = db_session.get(Project, test_project)
    sources = {
        name: KnowledgeSource(name=name, type=kind, project_id=test_project, team_id=proj.team_id)
        for name, kind in (("handbuch", "Local"), ("tickets", "Jira"), ("repo", "Git"))
    }
    db_session.add_all(sources.values())
    db_session.flush()
    entities = [
        CodeEntity(project_id=test_project, file_path="A.cbl", name="A", type="program"),
        CodeEntity(project_id=test_project, file_path="A.cbl", name="S1", type="section"),
        CodeEntity(project_id=test_project, file_path="A.cbl", name="S2", type="section"),
        CodeEntity(project_id=test_project, file_path="A.cbl", name="P1", type="paragraph"),
        CodeEntity(project_id=test_project, file_path="B.java", name="b", type="method"),
        CodeEntity(project_id=test_project, file_path="doc.adoc", name="d", type="doc_section"),
    ]

    def chunk(source, path, language=None):
        return DocumentChunk(
            project_id=test_project,
            source_id=sources[source].id,
            file_path=path,
            content="Text",
            metadata_json={"language": language} if language else {},
        )

    chunks = [
        chunk("handbuch", "handbuch.pdf"),
        chunk("handbuch", "handbuch.pdf"),
        chunk("tickets", "PROJ-1"),
        chunk("repo", "src/A.cbl", "cobol"),
        chunk("repo", "README.md", "markdown"),
    ]
    db_session.add_all([*entities, *chunks])
    db_session.commit()
    yield sources
    db_session.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == test_project).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == test_project).delete()
    for source in sources.values():
        db_session.delete(source)
    db_session.commit()


def test_scope_options_group_types_by_language_and_list_documentation_sources(
    client, test_project, mixed_project
):
    res = client.get(f"/projects/{test_project}/link-recommendations/scope-options")
    assert res.status_code == 200
    data = res.json()
    languages = {item["language"]: item for item in data["languages"]}
    assert set(languages) == {"cobol", "java"}
    assert languages["cobol"]["types"] == [
        {"type": "section", "count": 2},
        {"type": "paragraph", "count": 1},
        {"type": "program", "count": 1},
    ]
    sources = {item["name"]: item for item in data["doc_sources"]}
    # Im Git-Repo zählt nur die Doku-Datei, nicht der Quellcode.
    assert {name: item["chunk_count"] for name, item in sources.items()} == {
        "handbuch": 2,
        "tickets": 1,
        "repo": 1,
    }
    assert sources["tickets"]["type"] == "Jira"
    assert data["last_filter"] is None


def test_targeted_estimate_counts_both_chosen_sets(client, test_project, mixed_project):
    res = client.get(
        f"/projects/{test_project}/link-recommendations/estimate",
        params={
            "entity_types": ["program", "section"],
            "doc_source_ids": [mixed_project["handbuch"].id, mixed_project["tickets"].id],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_targeted"] is True
    assert (data["entity_count"], data["chunk_count"], data["entities_to_scan"]) == (3, 3, 3)
    assert data["has_active_run"] is False


def test_compute_records_the_filter_and_options_remember_it(
    client, db_session, test_project, mixed_project
):
    handbook = mixed_project["handbuch"].id
    with patch.object(entity_links_api, "send_tracked_task"):
        res = client.post(
            f"/projects/{test_project}/link-recommendations/compute",
            params={
                "entity_types": ["section", "program", "section"],
                "doc_source_ids": [handbook],
            },
        )
    assert res.status_code == 200
    run = db_session.get(LinkBuilderRun, res.json()["run_id"])
    expected = {"entity_types": ["program", "section"], "doc_source_ids": [handbook]}
    assert run.scope_json["filter"] == expected

    options = client.get(f"/projects/{test_project}/link-recommendations/scope-options").json()
    assert options["last_filter"] == expected


def test_compute_without_selection_stays_an_unrestricted_run(
    client, db_session, test_project, mixed_project
):
    with patch.object(entity_links_api, "send_tracked_task"):
        res = client.post(f"/projects/{test_project}/link-recommendations/compute")
    run = db_session.get(LinkBuilderRun, res.json()["run_id"])
    assert "filter" not in run.scope_json


def test_selection_rejects_foreign_sources_and_documentation_types(
    client, db_session, test_project, mixed_project
):
    other_team = Team(name="link-scope-other-team")
    db_session.add(other_team)
    db_session.flush()
    foreign = KnowledgeSource(name="fremd", type="Jira", team_id=other_team.id)
    db_session.add(foreign)
    db_session.commit()
    try:
        with patch.object(entity_links_api, "send_tracked_task") as send:
            foreign_res = client.post(
                f"/projects/{test_project}/link-recommendations/compute",
                params={"doc_source_ids": [foreign.id]},
            )
            doc_res = client.post(
                f"/projects/{test_project}/link-recommendations/compute",
                params={"entity_types": ["doc_section"]},
            )
        assert foreign_res.status_code == 422
        assert doc_res.status_code == 422
        send.assert_not_called()
    finally:
        db_session.delete(foreign)
        db_session.delete(other_team)
        db_session.commit()
