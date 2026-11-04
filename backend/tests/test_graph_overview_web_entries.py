"""Einträge der Web-Quellen eines Projekts sind eigene Knoten der Übersicht, auch ohne Verknüpfung."""

from doctus_models.database import DocumentChunk, KnowledgeSource


def _source(db_session, project, team, kind, url):
    source = KnowledgeSource(name=kind, type=kind, url=url, project_id=project, team_id=team)
    db_session.add(source)
    db_session.flush()
    return source


def _chunk(db_session, project, source, key, **meta):
    db_session.add(
        DocumentChunk(
            project_id=project,
            source_id=source.id,
            file_path=key,
            content="Text",
            start_line=1,
            end_line=1,
            metadata_json=meta,
        )
    )


def test_issues_and_pages_are_nodes_without_links_but_attachments_and_files_are_not(
    client, db_session, test_project, test_team
):
    gitlab = _source(db_session, test_project, test_team, "GitLabIssues", "https://gl.example")
    wiki = _source(db_session, test_project, test_team, "Confluence", "https://wiki.example")
    local = _source(db_session, test_project, test_team, "Local", None)
    issue_url = "https://gl.example/team/app/-/work_items/1"
    # Ein Issue mit zwei Abschnitten bleibt ein Knoten.
    _chunk(db_session, test_project, gitlab, "7/issues/1", title="#1: Absturz", url=issue_url)
    _chunk(db_session, test_project, gitlab, "7/issues/1#2", title="#1: Absturz", url=issue_url)
    _chunk(
        db_session,
        test_project,
        gitlab,
        "7/issues/2",
        title="#2: Ursache",
        url=f"{issue_url[:-1]}2",
    )
    _chunk(db_session, test_project, wiki, "ENG/5", title="Runbook", page_id="5")
    _chunk(
        db_session,
        test_project,
        wiki,
        "ENG/5/attachments/9",
        title="plan.pdf",
        page_id="5",
        attachment_filename="plan.pdf",
    )
    _chunk(db_session, test_project, local, "handbuch.md", title="handbuch.md")
    db_session.commit()

    try:
        response = client.get("/graph", params={"project_id": test_project})
        assert response.status_code == 200
        docs = [n for n in response.json()["nodes"] if n["type"] == "document"]
        by_label = {n["label"]: n for n in docs}
        assert sorted(by_label) == ["#1: Absturz", "#2: Ursache", "Runbook"]
        assert all(n["web_entry"] for n in docs)
        assert by_label["#1: Absturz"]["resource_type"] == "web_entry"
        assert by_label["#1: Absturz"]["url"] == issue_url
        assert by_label["Runbook"]["resource_type"] == "confluence_page"
    finally:
        for source in (gitlab, wiki, local):
            db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
            db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
