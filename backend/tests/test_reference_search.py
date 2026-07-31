"""
Regression coverage for backend/api/projects.py::_refs_for_document/_refs_for_file after
docs/GAPS.md #4: DocumentChunk.content is now Fernet-encrypted at rest (EncryptedString), so
these helpers can no longer filter with SQL ILIKE and instead match in Python after decryption
(see _ilike_to_regex). This proves the Python-side rewrite still finds the same matches the old
SQL ILIKE conditions did.
"""
from api.projects import _refs_for_document, _refs_for_file
from models.database import DocumentChunk


def test_refs_for_document_matches_decrypted_content(db_session, test_project):
    matching = DocumentChunk(
        project_id=test_project, source_id=None, file_path="src/main.py",
        content="See docs/spec.pdf for the full requirement.", start_line=10, end_line=10,
    )
    decoy = DocumentChunk(
        project_id=test_project, source_id=None, file_path="src/other.py",
        content="Nothing relevant here.", start_line=1, end_line=1,
    )
    db_session.add_all([matching, decoy])
    db_session.commit()

    try:
        refs = _refs_for_document(test_project, "docs/spec.pdf", "spec.pdf", db_session)
        assert [r["file_path"] for r in refs] == ["src/main.py"]
        assert refs[0]["line"] == 10
    finally:
        db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project).delete()
        db_session.commit()


def test_refs_for_file_matches_import_pattern_in_decrypted_content(db_session, test_project):
    matching = DocumentChunk(
        project_id=test_project, source_id=None, file_path="src/main.py",
        content='from helpers import format_date\nprint("ok")', start_line=1, end_line=2,
    )
    decoy = DocumentChunk(
        project_id=test_project, source_id=None, file_path="src/unrelated.py",
        content="helpers are nice but this line does not import anything", start_line=1, end_line=1,
    )
    db_session.add_all([matching, decoy])
    db_session.commit()

    try:
        refs = _refs_for_file(test_project, "src/helpers.py", "helpers", db_session)
        assert [r["file_path"] for r in refs] == ["src/main.py"]
    finally:
        db_session.query(DocumentChunk).filter(DocumentChunk.project_id == test_project).delete()
        db_session.commit()
