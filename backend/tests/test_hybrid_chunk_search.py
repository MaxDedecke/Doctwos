"""
Regression coverage for backend/api/chat.py::_hybrid_chunk_search's section-number match after
docs/GAPS.md #4: DocumentChunk.content is now Fernet-encrypted at rest, so the exact-match lookup
for a literal section number (e.g. "4.2.1") can no longer be a SQL ILIKE and instead scans
decrypted candidates in Python (see _SECTION_MATCH_SCAN_LIMIT). This proves it still finds the
chunk containing the section number without needing a real embedding call -- limit=1 means the
vector-search fallback branch is never reached.
"""
from api.chat import _hybrid_chunk_search
from models.database import DocumentChunk


def test_section_number_match_finds_decrypted_chunk(db_session, test_project):
    matching = DocumentChunk(
        project_id=test_project, file_path="docs/spec.pdf",
        content="Abschnitt 4.2.1: Brandschutzklasse T90 fuer tragende Waende.", start_line=1, end_line=1,
    )
    decoy = DocumentChunk(
        project_id=test_project, file_path="docs/other.pdf",
        content="Unrelated content without any section reference.", start_line=1, end_line=1,
    )
    db_session.add_all([matching, decoy])
    db_session.commit()

    try:
        base_query = db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project)
        results = _hybrid_chunk_search(
            base_query,
            query_embedding=[0.0] * 1024,
            query_text="Was verlangt Abschnitt 4.2.1 zur Brandschutzklasse?",
            limit=1,
        )
        assert len(results) == 1
        assert results[0].file_path == "docs/spec.pdf"
    finally:
        db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project).delete()
        db_session.commit()
