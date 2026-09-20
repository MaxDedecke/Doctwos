"""
Regression coverage for tasks/link_builder.py::_pass_keyword after docs/GAPS.md #4:
DocumentChunk.content is now Fernet-encrypted at rest (EncryptedString), so the keyword pass can
no longer filter with SQL ILIKE and instead scans the project's chunks in Python after
decryption. This is a real integration test against the shared Postgres DB (same one the backend
uses) since _pass_keyword's whole job is a DB query + decrypt + score.
"""

import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEdge, CodeEntity, DocumentChunk
from tasks.link_builder import (
    MIN_SCORE_KEYWORD,
    _build_entity_context,
    _build_relationship_index,
    _entity_breadcrumb,
    _pass_keyword,
)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_project(db_session):
    # Raw SQL, not the ORM, for teams/projects/knowledge_sources: parser/models/database.py has no
    # Team class (only backend does), so SQLAlchemy can't resolve Project.team_id's FK to a `teams`
    # table it doesn't know about and flushing a Project/KnowledgeSource ORM object here would raise
    # NoReferencedTableError -- pre-existing gap in the parser's model file, unrelated to this test.
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "link-builder-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": "link-builder-test-project", "team_id": team_id},
    ).scalar_one()
    source_id = db_session.execute(
        text(
            "INSERT INTO knowledge_sources (name, type, team_id, project_id, created_at) "
            "VALUES (:name, :type, :team_id, :project_id, now()) RETURNING id"
        ),
        {
            "name": "link-builder-test-source",
            "type": "Local",
            "team_id": team_id,
            "project_id": project_id,
        },
    ).scalar_one()
    db_session.commit()

    yield project_id, source_id

    db_session.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.execute(text("DELETE FROM knowledge_sources WHERE id = :id"), {"id": source_id})
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def test_pass_keyword_matches_decrypted_content(db_session, test_project):
    project_id, source_id = test_project

    entity = CodeEntity(
        project_id=project_id,
        file_path="src/payroll_calculator.py",
        name="calculate_payroll",
        type="function",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    matching = DocumentChunk(
        project_id=project_id,
        source_id=source_id,
        file_path="docs/payroll.pdf",
        content="This document describes the payroll calculator module in detail.",
    )
    decoy = DocumentChunk(
        project_id=project_id,
        source_id=source_id,
        file_path="docs/unrelated.pdf",
        content="Completely unrelated text about landscaping and gardens.",
    )
    db_session.add_all([matching, decoy])
    db_session.commit()

    result = _pass_keyword(entity, project_id, db_session)

    assert "docs/payroll.pdf" in result
    assert "docs/unrelated.pdf" not in result
    _, score = result["docs/payroll.pdf"]
    assert score >= MIN_SCORE_KEYWORD


def test_entity_context_uses_bounded_repository_excerpt_and_direct_edges(
    db_session, test_project
):
    project_id, source_id = test_project
    service = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentService.java",
        name="PaymentService",
        type="class",
        qualified_name="com.acme.PaymentService",
        start_line=1,
        end_line=6,
        meta_json={"language": "java"},
    )
    method = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentService.java",
        name="save",
        type="method",
        parent=service,
        qualified_name="com.acme.PaymentService#save(Payment)",
        start_line=2,
        end_line=4,
        meta_json={"language": "java", "signature": "save(Payment)"},
    )
    repository = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentRepository.java",
        name="PaymentRepository",
        type="class",
        qualified_name="com.acme.PaymentRepository",
    )
    db_session.add_all([service, method, repository])
    db_session.flush()
    db_session.add(
        CodeEdge(
            project_id=project_id,
            source_id=source_id,
            src_entity_id=method.id,
            dst_entity_id=repository.id,
            dst_name=repository.qualified_name,
            type="CALL",
            resolution="resolved",
        )
    )
    db_session.add(
        DocumentChunk(
            project_id=project_id,
            source_id=source_id,
            file_path="src/PaymentService.java",
            start_line=1,
            end_line=6,
            content=(
                "class PaymentService {\n"
                "  public Payment save(Payment payment) {\n"
                "    return repository.persist(payment);\n"
                "  }\n"
                "  public void unrelated() {}\n"
                "}\n"
            ),
        )
    )
    db_session.commit()

    entities_by_id = {service.id: service, method.id: method, repository.id: repository}
    relationships = _build_relationship_index(
        project_id, db_session, entities_by_id, {method.id}
    )
    context = _build_entity_context(
        method,
        project_id,
        db_session,
        _entity_breadcrumb(method, entities_by_id),
        relationships,
        {},
    )

    assert "Qualified name: com.acme.PaymentService#save(Payment)" in context
    assert "Breadcrumb: PaymentService › save" in context
    assert "signature: save(Payment)" in context
    assert "to CALL (resolved) com.acme.PaymentRepository" in context
    assert "return repository.persist(payment);" in context
    assert "unrelated" not in context
