"""Seitenweises Laden im Referenzen-Menü: /entities/{id}/neighbors (limit/group/after) und
/projects/{id}/references/page. Die Fixtures legen bewusst eindeutig benannte Daten an, damit die
Tests nicht von festen Namen (z. B. "Test Team") anderer Fixtures oder alter Testreste abhängen."""

import uuid

import pytest

from conftest import TEST_USERNAME
from models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeLink,
    KnowledgeSource,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)


@pytest.fixture
def paging_project(client, db_session):
    suffix = uuid.uuid4().hex[:10]
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    team = Team(name=f"paging-team-{suffix}")
    db_session.add(team)
    db_session.commit()
    db_session.add(TeamMembership(user_id=user.id, team_id=team.id))
    project = Project(name=f"paging-project-{suffix}", team_id=team.id, creator_id=user.id)
    db_session.add(project)
    db_session.commit()
    db_session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="admin"))
    source = KnowledgeSource(
        name=f"paging-source-{suffix}", type="Git", url="https://example.test/p.git", branch="main",
        project_id=project.id, team_id=team.id,
    )
    db_session.add(source)
    db_session.commit()
    yield project.id, source.id, team.id
    # Kindobjekte fallen per ON DELETE CASCADE mit dem Projekt bzw. der Quelle
    db_session.query(KnowledgeLink).filter(KnowledgeLink.source_a_title.like(f"paging-{suffix}%")).delete(synchronize_session=False)
    db_session.query(ProjectMembership).filter(ProjectMembership.project_id == project.id).delete()
    db_session.query(Project).filter(Project.id == project.id).delete()
    db_session.query(TeamMembership).filter(TeamMembership.team_id == team.id).delete()
    db_session.query(Team).filter(Team.id == team.id).delete()
    db_session.commit()


def _entity(db, project_id, source_id, name, file_path="MAIN.CBL", **extra):
    entity = CodeEntity(
        project_id=project_id, source_id=source_id, file_path=file_path, name=name, qualified_name=name,
        type="paragraph", start_line=1, end_line=2, **extra,
    )
    db.add(entity)
    db.flush()
    return entity


def _edge(db, project_id, source_id, src, dst, edge_type):
    edge = CodeEdge(
        project_id=project_id, source_id=source_id, src_entity_id=src.id, dst_entity_id=dst.id,
        dst_name=dst.name, type=edge_type, resolution="resolved", src_start_line=3, src_end_line=3,
    )
    db.add(edge)
    db.flush()
    return edge


@pytest.fixture
def busy_entity(paging_project, db_session):
    """Ein Objekt mit 5 ausgehenden CALL-, 2 ausgehenden COPY- und 3 eingehenden CALL-Kanten."""
    project_id, source_id, _ = paging_project
    center = _entity(db_session, project_id, source_id, "CENTER")
    out_calls = [_edge(db_session, project_id, source_id, center, _entity(db_session, project_id, source_id, f"OUT{i}"), "CALL") for i in range(5)]
    copies = [_edge(db_session, project_id, source_id, center, _entity(db_session, project_id, source_id, f"CPY{i}", file_path="X.CPY"), "COPY") for i in range(2)]
    in_calls = [_edge(db_session, project_id, source_id, _entity(db_session, project_id, source_id, f"IN{i}"), center, "CALL") for i in range(3)]
    db_session.commit()
    return center, project_id, {"CALL:out": [e.id for e in out_calls], "COPY:out": [e.id for e in copies], "CALL:in": [e.id for e in in_calls]}


def _ids(items):
    return [item["edge_id"] for item in items]


def test_neighbors_without_limit_keeps_the_complete_legacy_response(client, busy_entity):
    center, project_id, expected = busy_entity
    body = client.get(f"/entities/{center.id}/neighbors?project_id={project_id}").json()

    assert "page" not in body
    assert {key: _ids(items) for key, items in body["groups"].items()} == expected


def test_neighbors_with_limit_returns_page_info_and_the_first_items_per_group(client, busy_entity):
    center, project_id, expected = busy_entity
    body = client.get(f"/entities/{center.id}/neighbors?project_id={project_id}&limit=2").json()

    assert _ids(body["groups"]["CALL:out"]) == expected["CALL:out"][:2]
    assert body["page"]["CALL:out"] == {"total": 5, "has_more": True, "next_after": expected["CALL:out"][1]}
    assert body["page"]["CALL:in"] == {"total": 3, "has_more": True, "next_after": expected["CALL:in"][1]}
    assert body["page"]["COPY:out"] == {"total": 2, "has_more": False, "next_after": expected["COPY:out"][1]}


def test_neighbors_group_cursor_loads_the_remaining_items_without_gaps_or_duplicates(client, busy_entity):
    center, project_id, expected = busy_entity
    collected: list[int] = []
    after = None
    while True:
        url = f"/entities/{center.id}/neighbors?project_id={project_id}&limit=2&group=CALL:out"
        if after is not None:
            url += f"&after={after}"
        body = client.get(url).json()
        assert list(body["groups"]) == ["CALL:out"] or not body["groups"]
        collected += _ids(body["groups"].get("CALL:out", []))
        page = body["page"].get("CALL:out")
        if not page or not page["has_more"]:
            break
        after = page["next_after"]

    assert collected == expected["CALL:out"]


def test_neighbors_cursor_is_stable_when_an_edge_is_added_between_pages(client, db_session, busy_entity, paging_project):
    center, project_id, expected = busy_entity
    _, source_id, _ = paging_project
    first = client.get(f"/entities/{center.id}/neighbors?project_id={project_id}&limit=2&group=CALL:out").json()
    cursor = first["page"]["CALL:out"]["next_after"]

    # neue Kante vor dem Cursor (kleinere ID ist nicht möglich) und eine dahinter
    late = _edge(db_session, project_id, source_id, center, _entity(db_session, project_id, source_id, "LATE"), "CALL")
    db_session.commit()
    second = client.get(f"/entities/{center.id}/neighbors?project_id={project_id}&limit=10&group=CALL:out&after={cursor}").json()

    assert _ids(second["groups"]["CALL:out"]) == expected["CALL:out"][2:] + [late.id]


def test_neighbors_type_direction_and_contains_behave_as_before(client, db_session, paging_project):
    project_id, source_id, _ = paging_project
    parent = _entity(db_session, project_id, source_id, "PARENT", file_path="P.CBL")
    center = _entity(db_session, project_id, source_id, "CENTERC", file_path="P.CBL", parent_id=parent.id)
    caller = _entity(db_session, project_id, source_id, "CALLERC", file_path="C.CBL")
    callee = _entity(db_session, project_id, source_id, "CALLEEC", file_path="D.CBL")
    incoming = _edge(db_session, project_id, source_id, caller, center, "CALL")
    outgoing = _edge(db_session, project_id, source_id, center, callee, "COPY")
    db_session.commit()
    base = f"/entities/{center.id}/neighbors?project_id={project_id}"

    only_in = client.get(base + "&types=CALL&direction=in").json()
    assert list(only_in["groups"]) == ["CALL:in"]
    item = only_in["groups"]["CALL:in"][0]
    assert item["entity"]["id"] == caller.id
    assert item["reference"] == {
        "entity_id": caller.id, "name": caller.name, "file_path": caller.file_path,
        "source_id": source_id, "start_line": 3, "end_line": 3,
    }

    only_out = client.get(base + "&types=COPY&direction=out").json()
    assert list(only_out["groups"]) == ["COPY:out"]
    assert only_out["groups"]["COPY:out"][0]["edge_id"] == outgoing.id
    assert only_out["groups"]["COPY:out"][0]["entity"]["id"] == callee.id

    contains = client.get(base + "&types=CONTAINS").json()
    assert list(contains["groups"]) == ["CONTAINS:in"]
    assert contains["groups"]["CONTAINS:in"][0]["entity"]["id"] == parent.id
    assert incoming.id  # Kante existiert, gehört aber nicht zur CONTAINS-Auswahl


def test_neighbors_validates_paging_parameters(client, busy_entity):
    center, project_id, _ = busy_entity
    base = f"/entities/{center.id}/neighbors?project_id={project_id}"
    assert client.get(base + "&limit=0").status_code == 422
    assert client.get(base + "&limit=201").status_code == 422
    assert client.get(base + "&group=nonsense").status_code == 422


def test_neighbors_doc_group_is_paged_with_a_cursor(client, db_session, paging_project):
    project_id, source_id, _ = paging_project
    entity = _entity(db_session, project_id, source_id, "DOCENT")
    links = []
    for i in range(4):
        link = EntityDocLink(project_id=project_id, entity_id=entity.id, doc_title=f"Doc {i}", status="approved", score=0.9)
        db_session.add(link)
        db_session.flush()
        links.append(link.id)
    db_session.commit()

    first = client.get(f"/entities/{entity.id}/neighbors?project_id={project_id}&limit=3").json()
    assert [item["edge_id"] for item in first["groups"]["DOC:out"]] == [f"edl:{i}" for i in links[:3]]
    assert first["page"]["DOC:out"]["has_more"] is True
    assert first["page"]["DOC:out"]["total"] is None

    rest = client.get(f"/entities/{entity.id}/neighbors?project_id={project_id}&limit=3&group=DOC:out&after={first['page']['DOC:out']['next_after']}").json()
    assert [item["edge_id"] for item in rest["groups"]["DOC:out"]] == [f"edl:{links[3]}"]
    assert rest["page"]["DOC:out"]["has_more"] is False


@pytest.fixture
def file_with_references(paging_project, db_session):
    """Datei MAIN.CBL mit 5 verknüpften Dokumenten (EntityDocLink) und einer Wissensverknüpfung, dazu
    zwei Wissensverknüpfungen zu einer anderen Datei, die nicht auftauchen dürfen."""
    project_id, source_id, _ = paging_project
    suffix = uuid.uuid4().hex[:6]
    main = _entity(db_session, project_id, source_id, "MAINPARA")
    other = _entity(db_session, project_id, source_id, "OTHERPARA", file_path="OTHER.CBL")
    for i in range(5):
        db_session.add(EntityDocLink(project_id=project_id, entity_id=main.id, doc_title=f"paging-{suffix}-doc-{i}", status="approved", score=0.8))
    for i in range(2):
        db_session.add(KnowledgeLink(
            source_a_type="entity", source_a_entity_id=other.id, source_a_title=f"paging-{suffix}-other-{i}",
            source_b_type="document", source_b_title=f"paging-{suffix}-elsewhere-{i}", status="approved",
        ))
    db_session.add(KnowledgeLink(
        source_a_type="entity", source_a_entity_id=main.id, source_a_title=f"paging-{suffix}-main",
        source_b_type="document", source_b_title=f"paging-{suffix}-linked-doc", status="approved",
    ))
    db_session.commit()
    return project_id, suffix


def test_references_page_slices_the_deduplicated_list_and_reports_the_total(client, file_with_references):
    project_id, suffix = file_with_references
    url = f"/projects/{project_id}/references/page?file_path=MAIN.CBL"

    first = client.get(url + "&limit=4&offset=0").json()
    second = client.get(url + "&limit=4&offset=4").json()

    assert first["total"] == second["total"] == 6
    assert len(first["references"]) == 4 and len(second["references"]) == 2
    assert first["has_more"] is True and second["has_more"] is False
    titles = [r["title"] for r in first["references"] + second["references"]]
    assert len(set(titles)) == 6
    assert f"paging-{suffix}-linked-doc" in titles
    assert not any("elsewhere" in title or "other" in title for title in titles)


def test_references_page_matches_the_complete_endpoint(client, file_with_references):
    project_id, _ = file_with_references
    complete = client.get(f"/projects/{project_id}/references?file_path=MAIN.CBL").json()
    paged = client.get(f"/projects/{project_id}/references/page?file_path=MAIN.CBL&limit=100").json()

    assert paged["references"] == complete
    assert paged["total"] == len(complete)


def test_references_page_validates_limits_and_project_access(client, file_with_references):
    project_id, _ = file_with_references
    base = f"/projects/{project_id}/references/page?file_path=MAIN.CBL"
    assert client.get(base + "&limit=0").status_code == 422
    assert client.get(base + "&limit=101").status_code == 422
    assert client.get(base + "&offset=-1").status_code == 422
    assert client.get("/projects/99999999/references/page?file_path=MAIN.CBL").status_code == 404


def test_references_prefilter_matches_document_sides_and_entity_name_like_the_python_check(client, db_session, paging_project):
    project_id, source_id, _ = paging_project
    suffix = uuid.uuid4().hex[:6]
    entity = _entity(db_session, project_id, source_id, "NARROW", file_path="DOCSIDE.CBL")
    chunk = DocumentChunk(project_id=project_id, source_id=source_id, file_path="DOCSIDE.CBL", content="text", start_line=1, end_line=2)
    db_session.add(chunk)
    db_session.flush()
    # Dokument-Seite (Chunk der Datei) verknüpft mit einer Entity einer anderen Datei
    other = _entity(db_session, project_id, source_id, "ELSE", file_path="ELSE.CBL")
    db_session.add(KnowledgeLink(
        source_a_type="document", source_a_chunk_id=chunk.id, source_a_title=f"paging-{suffix}-chunk-side",
        source_b_type="entity", source_b_entity_id=other.id, source_b_title=f"paging-{suffix}-entity-side", status="approved",
    ))
    # Entity-Seite der Datei, aber mit anderem Namen als bei entity_name
    db_session.add(KnowledgeLink(
        source_a_type="entity", source_a_entity_id=entity.id, source_a_title=f"paging-{suffix}-named",
        source_b_type="document", source_b_title=f"paging-{suffix}-doc", status="approved",
    ))
    db_session.commit()
    base = f"/projects/{project_id}/references?file_path=DOCSIDE.CBL"

    all_titles = {r["title"] for r in client.get(base).json()}
    narrowed = {r["title"] for r in client.get(base + "&entity_name=OTHER-NAME").json()}

    assert f"paging-{suffix}-entity-side" in all_titles
    assert f"paging-{suffix}-doc" in all_titles
    # entity_name schränkt nur die Entity-Seite ein; die Dokument-Seite des Chunks bleibt erhalten
    assert f"paging-{suffix}-entity-side" in narrowed
    assert f"paging-{suffix}-doc" not in narrowed
