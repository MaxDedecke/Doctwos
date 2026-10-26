import uuid
from types import SimpleNamespace

from models.database import Team, Project, KnowledgeSource, CodeEntity, CodeEdge, DocumentChunk
from services.document_includes import selected_excerpts
from services.graph_retrieval import expand_chunks_with_graph


def test_selected_excerpts_keep_original_physical_lines_without_mutating_the_chunk():
    original = SimpleNamespace(content="eins\nzwei\ndrei\nvier", start_line=10, end_line=13, id=7)
    excerpts = selected_excerpts(original, [[11, 11], [13, 13]])
    assert [(e.content, e.start_line, e.end_line) for e in excerpts] == [
        ("zwei", 11, 11),
        ("vier", 13, 13),
    ]
    assert original.content == "eins\nzwei\ndrei\nvier" and excerpts[0].id == 7


def test_nested_includes_retrieve_only_selected_code_and_stay_source_scoped(db_session):
    db = db_session
    team = Team(name="includes-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="includes", team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(name="docs", type="Git", team_id=team.id, project_id=project.id)
    other = KnowledgeSource(name="other", type="Git", team_id=team.id, project_id=project.id)
    db.add_all([source, other])
    db.flush()
    try:

        def entity(path, kind, start=1, end=3, source_id=None):
            row = CodeEntity(
                project_id=project.id,
                source_id=source_id or source.id,
                file_path=path,
                name=path,
                type=kind,
                qualified_name=path + ":" + kind,
                start_line=start,
                end_line=end,
                variant_key="default",
            )
            db.add(row)
            db.flush()
            return row

        book = entity("guide.adoc", "asciidoc_document")
        chapter = entity("chapter.adoc", "asciidoc_document")
        section = entity("chapter.adoc", "doc_section")
        code = entity("Example.java", "compilation_unit")
        foreign = entity("foreign.adoc", "asciidoc_document", source_id=other.id)
        for src, dst, ranges in [
            (book, chapter, []),
            (section, code, [[2, 2]]),
            (book, foreign, []),
        ]:
            db.add(
                CodeEdge(
                    project_id=project.id,
                    source_id=source.id,
                    variant_key="default",
                    src_entity_id=src.id,
                    dst_entity_id=dst.id,
                    dst_name=dst.name,
                    type="INCLUDES",
                    resolution="resolved",
                    src_start_line=1,
                    src_end_line=1,
                    meta_json={"language": "asciidoc", "selection_ranges": ranges},
                )
            )
        chunks = []
        for row, content in [
            (book, "include::chapter.adoc[]"),
            (chapter, "include::Example.java[]"),
            (code, "outside\nwanted\noutside"),
            (foreign, "private-other-source"),
        ]:
            chunk = DocumentChunk(
                project_id=project.id,
                source_id=row.source_id,
                file_path=row.file_path,
                content=content,
                start_line=1,
                end_line=3,
                metadata_json={"language": "text"},
            )
            db.add(chunk)
            chunks.append(chunk)
        db.commit()
        expanded = expand_chunks_with_graph(db, [chunks[0]], token_budget=1000)
        selected = next(c for c in expanded if c.file_path == "Example.java")
        assert selected.content == "wanted" and selected.start_line == selected.end_line == 2
        assert not any(c.file_path == "foreign.adoc" for c in expanded)
        assert db.get(DocumentChunk, chunks[2].id).content == "outside\nwanted\noutside"
    finally:
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
