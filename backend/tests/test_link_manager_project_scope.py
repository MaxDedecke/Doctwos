import pytest

from doctus_models.database import DocumentChunk, KnowledgeLink, LinkBuilderRun, Project, Topic


@pytest.fixture
def scoped_links(db_session, test_project):
    project = db_session.get(Project, test_project)
    other = Project(name="Link scope other", team_id=project.team_id)
    db_session.add(other)
    db_session.flush()
    chunks = [
        DocumentChunk(project_id=p, file_path=f"scope-{i}.md", content="Scope")
        for i, p in enumerate([test_project, test_project, other.id, other.id])
    ]
    db_session.add_all(chunks)
    db_session.flush()
    links = [
        KnowledgeLink(
            source_a_type="document",
            source_b_type="document",
            source_a_chunk_id=chunks[a].id,
            source_b_chunk_id=chunks[b].id,
            source_a_title=f"Scope {a}",
            source_b_title=f"Scope {b}",
            status=status,
            score=0.8,
        )
        for a, b, status in [
            (0, 1, "pending"),
            (2, 3, "pending"),
            (0, 2, "pending"),
            (0, 1, "approved"),
        ]
    ]
    links.append(
        KnowledgeLink(
            project_id=test_project,
            source_a_type="document",
            source_b_type="document",
            source_a_title="Manual A",
            source_b_title="Manual B",
            status="rejected",
        )
    )
    db_session.add_all(links)
    db_session.commit()
    yield {
        "project": test_project,
        "other": other.id,
        "chunks": [c.id for c in chunks],
        "links": [item.id for item in links],
    }
    db_session.query(KnowledgeLink).filter(
        KnowledgeLink.id.in_([item.id for item in links])
    ).delete(synchronize_session=False)
    db_session.query(DocumentChunk).filter(DocumentChunk.id.in_([c.id for c in chunks])).delete(
        synchronize_session=False
    )
    db_session.query(Project).filter(Project.id == other.id).delete()
    db_session.commit()


def test_project_lists_counts_and_score_exclude_other_and_cross_project_links(client, scoped_links):
    scope = scoped_links
    for project, expected in [
        (scope["project"], scope["links"][0]),
        (scope["other"], scope["links"][1]),
    ]:
        response = client.get(f"/knowledge-links?project_id={project}&status=pending")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == [expected]
        counts = client.get(f"/knowledge-links/counts?project_id={project}").json()
        assert counts == (
            {"pending": 1, "approved": 1, "rejected": 1}
            if project == scope["project"]
            else {"pending": 1, "approved": 0, "rejected": 0}
        )
        assert client.get(f"/knowledge-links?project_id={project}&min_score=0.9").json() == []
        assert client.get(f"/knowledge-links/counts?project_id={project}&min_score=0.9").json() == {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
        }


def test_project_scope_checks_access_and_existence(scoped_links, member_client, db_session):
    for path in ["/knowledge-links", "/knowledge-links/counts"]:
        assert member_client.get(f"{path}?project_id=2147483647").status_code == 404
        assert member_client.get(f"{path}?project_id={scoped_links['other']}").status_code in [
            403,
            404,
        ]


def test_manual_link_keeps_project_and_rejects_foreign_endpoint(client, scoped_links, db_session):
    scope = scoped_links
    payload = dict(
        source_a_type="document",
        source_b_type="document",
        source_a_title="Manual scope",
        source_b_title="Other",
    )
    wrong = client.post(
        f"/knowledge-links?project_id={scope['project']}",
        json={
            **payload,
            "source_a_chunk_id": scope["chunks"][0],
            "source_b_chunk_id": scope["chunks"][2],
        },
    )
    assert wrong.status_code == 422
    response = client.post(f"/knowledge-links?project_id={scope['project']}", json=payload)
    assert response.status_code == 200
    link_id = response.json()["id"]
    try:
        assert db_session.get(KnowledgeLink, link_id).project_id == scope["project"]
        assert link_id in [
            item["id"]
            for item in client.get(f"/knowledge-links?project_id={scope['project']}").json()
        ]
        assert link_id not in [
            item["id"]
            for item in client.get(f"/knowledge-links?project_id={scope['other']}").json()
        ]
    finally:
        db_session.query(KnowledgeLink).filter(KnowledgeLink.id == link_id).delete()
        db_session.commit()


def test_run_history_is_project_specific(client, scoped_links, db_session):
    runs = [
        LinkBuilderRun(project_id=p, task_type="knowledge_links", status="completed")
        for p in [scoped_links["project"], scoped_links["other"]]
    ]
    db_session.add_all(runs)
    db_session.commit()
    try:
        result = client.get(f"/knowledge-links/runs?project_id={scoped_links['project']}")
        assert result.status_code == 200
        assert [r["id"] for r in result.json()] == [runs[0].id]
    finally:
        db_session.query(LinkBuilderRun).filter(LinkBuilderRun.id.in_([r.id for r in runs])).delete(
            synchronize_session=False
        )
        db_session.commit()


def test_topics_search_nodes_and_mutations_stay_in_project(client, scoped_links, db_session):
    p, other = scoped_links["project"], scoped_links["other"]
    response = client.post(f"/topics?project_id={p}", json={"name": "Project-only topic"})
    assert response.status_code == 201
    tid = response.json()["id"]
    try:
        assert db_session.get(Topic, tid).project_id == p
        assert tid in [t["id"] for t in client.get(f"/topics?project_id={p}").json()]
        assert tid not in [t["id"] for t in client.get(f"/topics?project_id={other}").json()]
        assert client.get(f"/topics/{tid}/nodes?project_id={other}").status_code == 404
        assert (
            client.patch(f"/topics/{tid}?project_id={other}", json={"name": "wrong"}).status_code
            == 404
        )
        assert client.delete(f"/topics/{tid}?project_id={other}").status_code == 404
        assert (
            client.post(
                f"/topics/{tid}/nodes?project_id={p}",
                json={"node_type": "project", "node_id": other, "node_label": "wrong"},
            ).status_code
            == 422
        )
        found = client.get(f"/topics/search-nodes?project_id={p}&types=project").json()
        assert [n["node_id"] for n in found] == [p]
        assert (
            client.post(
                f"/topics/{tid}/nodes?project_id={p}",
                json={"node_type": "project", "node_id": p, "node_label": "right"},
            ).status_code
            == 201
        )
    finally:
        db_session.query(Topic).filter(Topic.id == tid).delete()
        db_session.commit()


def test_foreign_project_cannot_review_modify_or_delete_a_link(client, scoped_links):
    link_id = scoped_links["links"][1]
    url = f"/knowledge-links/{link_id}?project_id={scoped_links['project']}"
    assert client.patch(url, json={"status": "approved"}).status_code == 404
    assert client.delete(url).status_code == 404
    assert (
        client.post(
            f"/knowledge-links/{link_id}/llm-review?project_id={scoped_links['project']}"
        ).status_code
        == 404
    )
