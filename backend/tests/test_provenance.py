from datetime import datetime, timezone
from types import SimpleNamespace

from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource
from services.change_package import _linked_documents
from services.provenance import build_provenance, source_revision


def test_source_revision_prefers_exact_commit_then_content_fingerprint():
    source = SimpleNamespace(
        spaces={"last_commit_hash": "spaces-commit"},
        sync_cursor={"last_commit": "cursor-commit"},
    )
    assert source_revision(source) == ("cursor-commit", "commit")
    assert source_revision(None, {"content_hash": "content-hash"}) == (
        "content-hash",
        "content_hash",
    )
    assert source_revision(None) == (None, None)


def test_provenance_keeps_link_review_separate_from_claim_verification():
    source = SimpleNamespace(
        id=7,
        name="Payment manual",
        type="Confluence",
        branch=None,
        spaces={},
        sync_cursor={},
        last_synced_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        sync_status="completed",
    )
    provenance = build_provenance(
        source,
        kind="document_claim",
        verification_status="unverified",
        association_status="approved",
        association_reviewed_at="2026-09-20T10:00:00+00:00",
        locator={"file_path": "Payments", "page": 4},
    )

    assert provenance["verification_status"] == "unverified"
    assert provenance["association_status"] == "approved"
    assert provenance["association_reviewed_at"] == "2026-09-20T10:00:00+00:00"
    assert provenance["source_name"] == "Payment manual"
    assert provenance["source_revision"] is None
    assert provenance["last_synced_at"] == "2026-09-21T00:00:00+00:00"


def test_approved_change_package_document_link_does_not_verify_its_claim(
    db_session, test_project, test_team
):
    code_source = KnowledgeSource(
        name="repo", type="Git", project_id=test_project, team_id=test_team
    )
    document_source = KnowledgeSource(
        name="Payment manual",
        type="Confluence",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add_all([code_source, document_source])
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=code_source.id,
        file_path="src/payment.py",
        name="authorize",
        type="method",
        start_line=1,
        end_line=10,
    )
    chunk = DocumentChunk(
        project_id=test_project,
        source_id=document_source.id,
        file_path="Payments/Rules",
        content="Payments must be authorized.",
        start_line=1,
        end_line=3,
        metadata_json={"page": 4, "section": "Authorization"},
        content_hash="chunk-hash",
    )
    db_session.add_all([entity, chunk])
    db_session.flush()
    link = EntityDocLink(
        project_id=test_project,
        entity_id=entity.id,
        chunk_id=chunk.id,
        doc_title="Payment rules",
        source_type="Confluence",
        status="approved",
        reviewed_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )
    db_session.add(link)
    db_session.commit()
    try:
        records, _ = _linked_documents(db_session, test_project, {entity.id})
        provenance = records[0]["evidence"]["provenance"]
        assert provenance["kind"] == "document_claim"
        assert provenance["verification_status"] == "unverified"
        assert provenance["association_status"] == "approved"
        assert provenance["association_reviewed_at"] == "2026-09-20T00:00:00+00:00"
        assert provenance["source_revision"] == "chunk-hash"
        assert provenance["revision_kind"] == "content_hash"
        assert provenance["locator"]["page"] == 4
        assert provenance["locator"]["section"] == "Authorization"
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(DocumentChunk).filter(DocumentChunk.id == chunk.id).delete()
        db_session.query(CodeEntity).filter(CodeEntity.id == entity.id).delete()
        db_session.query(KnowledgeSource).filter(
            KnowledgeSource.id.in_([code_source.id, document_source.id])
        ).delete(synchronize_session=False)
        db_session.commit()
