"""Analyse-Arbeitsfläche (`/projects/{id}/link-runs`): Facetten, Suche, Vorschau, Schätzung und Start mit Mengen."""

from unittest.mock import patch

import pytest

import services.link_run_start as link_run_start
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeSource,
    LinkBuilderRun,
    Project,
)
from doctus_models.link_sets import LinkSet, RunSets
from services.link_set_options import language_of_type
from tests import test_entity_links
from tests.test_entity_links import _as

project_member = test_entity_links.project_member  # Fixture eines Projektmitglieds ohne Adminrechte


def test_types_fall_into_their_language():
    assert language_of_type("program") == "cobol"
    assert language_of_type("section") == "cobol"
    assert language_of_type("copybook") == "cobol"
    assert language_of_type("method") == "java"
    assert language_of_type("compilation_unit") == "java"
    assert language_of_type("jcl_step") == "jcl"
    assert language_of_type("maven_module") == "maven"
    assert language_of_type("something_new") == "other"


def test_set_format_normalizes_and_rejects_unknown_parts():
    raw = {
        "kind": "code",
        "mode": "custom",
        "facets": {"entity_type": ["section", "program", "section", ""]},
        "items": [{"kind": "entity", "id": "7", "label": "X"}, {"kind": "entity", "id": 7}],
    }
    link_set = LinkSet.from_json(raw)
    assert link_set.facet("entity_type") == ("program", "section")
    assert [item.key for item in link_set.items] == [(7,)]
    assert LinkSet.from_json(link_set.to_json()) == link_set
    assert LinkSet.from_json({"kind": "code", "mode": "custom"}).is_empty
    for broken in (
        {"kind": "code", "mode": "custom", "facets": {"colour": ["red"]}},
        {"kind": "code", "mode": "custom", "facets": {"entity_type": ["doc_section"]}},
        {"kind": "docs", "mode": "custom", "items": [{"kind": "entity", "id": 1}]},
        {"kind": "docs", "mode": "custom", "items": [{"kind": "document", "source_id": 1}]},
        {"kind": "sql", "mode": "all"},
    ):
        with pytest.raises(ValueError):
            LinkSet.from_json(broken)
    with pytest.raises(ValueError):
        RunSets.from_json({"pairing": "code_docs", "a": {"kind": "docs", "mode": "all"}})


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
    repo = sources["repo"].id

    def entity(name, kind, path="A.cbl"):
        return CodeEntity(
            project_id=test_project, source_id=repo, file_path=path, name=name, type=kind
        )

    entities = {
        "A": entity("PAYCALC", "program"),
        "S1": entity("MAIN-SECTION", "section"),
        "S2": entity("END-SECTION", "section"),
        "P1": entity("INIT-PARA", "paragraph"),
        "M": entity("calculate", "method", "B.java"),
        "D": entity("Intro", "doc_section", "doc.adoc"),
    }

    def chunk(source, path, title=None, language=None):
        meta = {"title": title} if title else {}
        if language:
            meta["language"] = language
        return DocumentChunk(
            project_id=test_project,
            source_id=sources[source].id,
            file_path=path,
            content="Text",
            metadata_json=meta,
        )

    chunks = [
        chunk("handbuch", "handbuch.pdf", "Gehaltsabrechnung"),
        chunk("handbuch", "handbuch.pdf", "Gehaltsabrechnung"),
        chunk("tickets", "PROJ-1", "PROJ-1: Gehalt falsch"),
        chunk("repo", "src/A.cbl", language="cobol"),
        chunk("repo", "README.md", "README", "markdown"),
    ]
    db_session.add_all([*entities.values(), *chunks])
    db_session.commit()
    yield sources, entities
    db_session.query(LinkBuilderRun).filter(LinkBuilderRun.project_id == test_project).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == test_project).delete()
    for source in sources.values():
        db_session.delete(source)
    db_session.commit()


def _url(project_id, suffix=""):
    return f"/projects/{project_id}/link-runs{suffix}"


def test_options_group_facets_and_offer_document_pairs_only_to_admins(
    client, test_project, mixed_project
):
    data = client.get(_url(test_project, "/options")).json()
    assert [item["key"] for item in data["pairings"]] == ["code_docs", "docs_docs"]
    code = data["kinds"]["code"]
    assert code["total"] == 5
    entity_types = next(facet for facet in code["facets"] if facet["name"] == "entity_type")
    groups = {group["key"]: group for group in entity_types["groups"]}
    assert set(groups) == {"cobol", "java"}
    assert groups["cobol"]["values"] == [
        {"value": "section", "count": 2},
        {"value": "paragraph", "count": 1},
        {"value": "program", "count": 1},
    ]
    docs = data["kinds"]["docs"]
    sources = {
        value["label"]: value["count"]
        for group in docs["facets"][0]["groups"]
        for value in group["values"]
    }
    # Im Git-Repo zählt nur die Doku-Datei, nicht der Quellcode.
    assert sources == {"handbuch": 2, "tickets": 1, "repo": 1}
    assert data["last"] == {"code_docs": None, "docs_docs": None}


def test_options_hide_admin_pairings_from_members(
    unauthenticated_client, project_member, test_project, mixed_project
):
    data = _as(unauthenticated_client, project_member).get(_url(test_project, "/options")).json()
    assert [item["key"] for item in data["pairings"]] == ["code_docs"]
    assert set(data["kinds"]) == {"code", "docs"}


def test_search_finds_entities_and_documents_but_no_source_code_chunks(
    client, test_project, mixed_project
):
    code = client.get(_url(test_project, "/search"), params={"kind": "code", "q": "SECTION"})
    assert {item["label"] for item in code.json()["items"]} == {"MAIN-SECTION", "END-SECTION"}
    assert code.json()["items"][0]["group"] == "cobol"

    docs = client.get(_url(test_project, "/search"), params={"kind": "docs", "q": "gehalt"})
    items = docs.json()["items"]
    assert {(item["label"], item["group"]) for item in items} == {
        ("Gehaltsabrechnung", "Local"),
        ("PROJ-1: Gehalt falsch", "Jira"),
    }
    handbook = next(item for item in items if item["group"] == "Local")
    assert handbook["chunk_count"] == 2
    none = client.get(_url(test_project, "/search"), params={"kind": "docs", "q": "A.cbl"})
    assert none.json()["items"] == []


def test_preview_combines_facets_and_search_picks(client, test_project, mixed_project):
    _sources, entities = mixed_project
    body = {
        "set": {
            "kind": "code",
            "mode": "custom",
            "facets": {"entity_type": ["program"]},
            "items": [{"kind": "entity", "id": entities["M"].id}],
        }
    }
    data = client.post(_url(test_project, "/preview"), json=body).json()
    assert data["count"] == 2
    assert {item["label"] for item in data["sample"]} == {"PAYCALC", "calculate"}

    empty = client.post(
        _url(test_project, "/preview"), json={"set": {"kind": "code", "mode": "custom"}}
    )
    assert empty.json()["count"] == 0


def test_estimate_counts_both_sets(client, test_project, mixed_project):
    sources, _entities = mixed_project
    body = {
        "pairing": "code_docs",
        "a": {"kind": "code", "mode": "custom", "facets": {"entity_type": ["program", "section"]}},
        "b": {
            "kind": "docs",
            "mode": "custom",
            "items": [
                {
                    "kind": "document",
                    "source_id": sources["handbuch"].id,
                    "file_path": "handbuch.pdf",
                }
            ],
        },
    }
    data = client.post(_url(test_project, "/estimate"), json=body).json()
    assert data["targeted"] is True
    assert (data["a_count"], data["b_count"], data["reviews_max"]) == (3, 2, 3)

    unrestricted = client.post(_url(test_project, "/estimate"), json={"pairing": "code_docs"})
    assert unrestricted.json()["targeted"] is False


def test_start_stores_sets_and_options_remember_them(
    client, db_session, test_project, mixed_project
):
    sources, entities = mixed_project
    body = {
        "pairing": "code_docs",
        "a": {
            "kind": "code",
            "mode": "custom",
            "facets": {"entity_type": ["section"]},
            "items": [{"kind": "entity", "id": entities["A"].id, "label": "PAYCALC"}],
        },
        "b": {"kind": "docs", "mode": "custom", "facets": {"source": [sources["tickets"].id]}},
        "min_confidence": 60,
        "max_items": 50,
        "params": {"review_batch_size": 3},
    }
    with patch.object(link_run_start, "send_tracked_task") as send:
        res = client.post(_url(test_project), json=body)
    assert res.status_code == 200, res.text
    assert send.call_args.args[2] == "compute_entity_links"
    run = db_session.get(LinkBuilderRun, res.json()["run_id"])
    assert run.scope_json["params"] == {"review_batch_size": 3}
    assert run.scope_json["max_items"] == 50
    stored = run.scope_json["sets"]
    assert stored["a"]["items"] == [{"kind": "entity", "id": entities["A"].id, "label": "PAYCALC"}]
    assert stored["b"]["facets"] == {"source": [str(sources["tickets"].id)]}

    options = client.get(_url(test_project, "/options")).json()
    assert options["last"]["code_docs"] == stored


def test_start_without_selection_stays_the_incremental_run(
    client, db_session, test_project, mixed_project
):
    with patch.object(link_run_start, "send_tracked_task"):
        res = client.post(_url(test_project), json={"pairing": "code_docs"})
    run = db_session.get(LinkBuilderRun, res.json()["run_id"])
    assert "sets" not in run.scope_json


def test_start_rejects_empty_sets_unknown_parts_and_member_document_pairs(
    client, unauthenticated_client, project_member, test_project, mixed_project
):
    with patch.object(link_run_start, "send_tracked_task") as send:
        empty = client.post(
            _url(test_project),
            json={"pairing": "code_docs", "a": {"kind": "code", "mode": "custom"}},
        )
        unknown = client.post(_url(test_project), json={"pairing": "code_code"})
        member = _as(unauthenticated_client, project_member).post(
            _url(test_project), json={"pairing": "docs_docs"}
        )
    assert empty.status_code == 422 and "Menge A" in empty.json()["detail"]
    assert unknown.status_code == 422
    assert member.status_code == 403
    send.assert_not_called()


def test_document_pairs_queue_a_knowledge_run_with_sets(
    client, db_session, test_project, mixed_project
):
    sources, _entities = mixed_project
    body = {
        "pairing": "docs_docs",
        "a": {"kind": "docs", "mode": "custom", "facets": {"source": [sources["handbuch"].id]}},
        "b": {"kind": "docs", "mode": "custom", "facets": {"source": [sources["tickets"].id]}},
    }
    with patch.object(link_run_start, "send_tracked_task") as send:
        res = client.post(_url(test_project), json=body)
    assert res.status_code == 200, res.text
    assert send.call_args.args[2] == "compute_knowledge_links"
    run = db_session.get(LinkBuilderRun, res.json()["run_id"])
    assert run.task_type == "knowledge_links"
    assert run.scope_json["sets"]["pairing"] == "docs_docs"
