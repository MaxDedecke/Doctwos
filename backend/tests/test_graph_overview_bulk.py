"""The overview must not query/decrypt one document or vector per knowledge link."""

from sqlalchemy import event

from api.graph import _doc_node, _ensure_entity_file_node
from models.database import CodeEntity, DocumentChunk, KnowledgeLink, KnowledgeSource
from services.graph_overview_links import append_overview_knowledge_links


def test_overview_link_queries_are_constant_and_exclude_vectors(
    db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="bulk-graph", type="Local", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="A.java",
        name="A",
        qualified_name="A",
        type="class",
        start_line=1,
        end_line=2,
    )
    db_session.add(entity)
    db_session.flush()
    entity_id, source_id = entity.id, source.id
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def add_links(start, stop):
        for i in range(start, stop):
            chunk = DocumentChunk(
                project_id=test_project,
                source_id=source_id,
                file_path=f"guide-{i}.md",
                content="private source text",
            )
            db_session.add(chunk)
            db_session.flush()
            db_session.add(
                KnowledgeLink(
                    source_a_type="entity",
                    source_a_entity_id=entity_id,
                    source_a_title="A",
                    source_b_type="document",
                    source_b_chunk_id=chunk.id,
                    source_b_title=f"guide-{i}",
                    status="approved",
                    link_type="manual",
                )
            )
        db_session.commit()

    def load():
        db_session.expire_all()
        statements.clear()
        nodes, edges, preserved = {}, [], set()
        append_overview_knowledge_links(
            nodes,
            edges,
            preserved,
            db_session,
            "approved",
            test_project,
            [test_team],
            [test_project],
            _ensure_entity_file_node,
            _doc_node,
        )
        return nodes, edges

    try:
        add_links(0, 10)
        event.listen(db_session.bind, "before_cursor_execute", capture)
        _, small = load()
        small_count = len(statements)
        event.remove(db_session.bind, "before_cursor_execute", capture)
        add_links(10, 100)
        event.listen(db_session.bind, "before_cursor_execute", capture)
        nodes, large = load()
        assert len(small) == 10
        assert len(large) == 100
        assert len(nodes) == 101
        assert len(statements) == small_count
        assert small_count <= 5
        assert all(
            "document_chunks.embedding" not in s and "document_chunks.content" not in s
            for s in statements
        )
    finally:
        if event.contains(db_session.bind, "before_cursor_execute", capture):
            event.remove(db_session.bind, "before_cursor_execute", capture)
        db_session.query(KnowledgeLink).filter(
            KnowledgeLink.source_a_entity_id == entity_id
        ).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).delete()
        db_session.commit()
