"""Datei-Baum einer Wissensquelle ebenen- und seitenweise (Seitenleiste lädt beim Aufklappen)."""

import pytest

from codena_models.database import DocumentChunk, KnowledgeSource, SourceScanFile


@pytest.fixture
def source(client, test_project, db_session):
    created = []

    def _make(kind: str) -> int:
        response = client.post(
            "/knowledge-sources",
            json={"name": f"tree-{kind}", "type": kind, "project_id": test_project},
        )
        created.append(response.json()["id"])
        return created[-1]

    yield _make, test_project
    for source_id in created:
        db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).delete()
        db_session.query(SourceScanFile).filter(SourceScanFile.source_id == source_id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).delete()
    db_session.commit()


def test_a_flat_issue_source_pages_in_natural_order(client, source, db_session):
    make, project_id = source
    source_id = make("Jira")
    for number in (1, 2, 10, 3, 100):
        for part in ("", "#comment-1"):
            db_session.add(
                DocumentChunk(
                    project_id=project_id,
                    source_id=source_id,
                    file_path=f"SYNCOPE-{number}{part}",
                    content="x",
                    start_line=1,
                    end_line=1,
                )
            )
    db_session.commit()

    first = client.get(f"/knowledge-sources/{source_id}/tree", params={"limit": 3}).json()
    second = client.get(
        f"/knowledge-sources/{source_id}/tree", params={"limit": 3, "offset": first["next_offset"]}
    ).json()

    assert first["total"] == 5 and first["next_offset"] == 3
    assert [e["name"] for e in first["entries"]] == ["SYNCOPE-1", "SYNCOPE-2", "SYNCOPE-3"]
    assert [e["name"] for e in second["entries"]] == ["SYNCOPE-10", "SYNCOPE-100"]
    assert second["next_offset"] is None


def test_a_git_source_lists_one_level_from_the_scan_log_with_status(client, source, db_session):
    make, _ = source
    source_id = make("Git")
    for path, status in [
        ("app/cbl/PROG.cbl", "complete"),
        ("app/cbl/BROKEN.cbl", "text_fallback"),
        ("app/cpy/REC.cpy", "complete"),
        ("README_%.md", "complete"),
    ]:
        db_session.add(
            SourceScanFile(
                source_id=source_id,
                file_path=path,
                content_hash=path,
                parse_status=status,
                parse_error="Grammatikfehler" if status != "complete" else None,
                language="cobol",
            )
        )
    db_session.commit()

    root = client.get(f"/knowledge-sources/{source_id}/tree").json()
    app = client.get(f"/knowledge-sources/{source_id}/tree", params={"dir": "app"}).json()
    cbl = client.get(f"/knowledge-sources/{source_id}/tree", params={"dir": "app/cbl"}).json()
    # Ein "_" im Ordnernamen ist kein Platzhalter.
    escaped = client.get(f"/knowledge-sources/{source_id}/tree", params={"dir": "app_cbl"}).json()

    assert root["entries"] == [
        {"type": "dir", "name": "app", "path": "app", "files": 3},
        {"type": "file", "name": "README_%.md", "path": "README_%.md"},
    ]
    assert [(e["type"], e["name"], e["files"]) for e in app["entries"]] == [
        ("dir", "cbl", 2),
        ("dir", "cpy", 1),
    ]
    assert cbl["entries"][0]["status"]["status"] == "text_fallback"
    assert "status" not in cbl["entries"][1]
    assert escaped["entries"] == [] and escaped["total"] == 0
    summary = client.get(f"/knowledge-sources/{source_id}/scan-summary").json()
    assert summary["total_files"] == 4 and summary["by_status"]["text_fallback"] == 1


def test_the_tree_uses_the_same_visibility_as_the_file_list(member_client, source):
    make, _ = source
    source_id = make("Git")

    tree = member_client.get(f"/knowledge-sources/{source_id}/tree").status_code
    files = member_client.get(f"/knowledge-sources/{source_id}/files").status_code
    assert tree == files
    assert member_client.get("/knowledge-sources/999999/tree").status_code == 404
