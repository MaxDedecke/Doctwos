"""O-380: Gründe nicht strukturierter Dateien und Kantenlage je Quelle."""

import pytest

from core.scan_report import classify_reason, summarize_edges, summarize_scan_reasons
from models.database import CodeEdge, CodeEntity, KnowledgeSource


@pytest.mark.parametrize(
    "status,error,category",
    [
        ("skipped", "Binärformat ohne Textextraktion, wird nicht embedded.", "not_indexable"),
        ("skipped", None, "not_indexable"),
        ("text_fallback", "Sprache 'properties' hat keinen Strukturparser; als Text indexiert.", "no_structure_parser"),
        ("partial", "Strukturparser fehlgeschlagen: IndexError: list index out of range (declarations.py:288 in walk)", "parser_error"),
        ("partial", "no viable alternative at input 'PARM-DATE,'", "parser_error"),
        ("partial", "DOCTYPE/DTD-Deklarationen werden aus Sicherheitsgründen nicht verarbeitet.", "blocked_for_safety"),
        ("partial", "1 Codebereich(e) außerhalb erkannter Paragraphen nur als Text erfasst: Zeilen 5-6.", "uncovered_code"),
        ("partial", "etwas Unbekanntes", "other"),
    ],
)
def test_reason_categories(status, error, category):
    assert classify_reason(status, error) == category


def test_summary_counts_by_category_language_and_parser_error_class():
    rows = [
        ("java", "complete", None),
        ("java", "partial", "Strukturparser fehlgeschlagen: IndexError: x (a.py:1 in f)"),
        ("java", "partial", "Strukturparser fehlgeschlagen: IndexError: y (a.py:1 in f)"),
        ("properties", "text_fallback", "Sprache 'properties' hat keinen Strukturparser; als Text indexiert."),
        (None, "skipped", None),
    ]
    summary = summarize_scan_reasons(rows)
    assert summary["by_reason"] == {
        "no_structure_parser": {"total_files": 1, "by_language": {"properties": 1}},
        "not_indexable": {"total_files": 1, "by_language": {"unknown": 1}},
        "parser_error": {"total_files": 2, "by_language": {"java": 2}},
    }
    assert summary["parser_error_classes"] == {"IndexError": 2}


def test_edge_summary_separates_external_targets_from_open_gaps(db_session, test_project, test_team):
    source = KnowledgeSource(project_id=test_project, team_id=test_team, type="Git", name="edges")
    db_session.add(source)
    db_session.commit()
    entity = CodeEntity(source_id=source.id, project_id=test_project, file_path="a.cbl", name="A",
                        type="program", qualified_name="A", start_line=1, end_line=2)
    db_session.add(entity)
    db_session.commit()

    def edge(dst, resolution, meta=None):
        return CodeEdge(source_id=source.id, project_id=test_project, src_entity_id=entity.id,
                        dst_name=dst, type="CALL", resolution=resolution, meta_json=meta)

    db_session.add_all([
        edge("DFHAID", "unresolved", {"external": {"category": "cics"}}),
        edge("MQOPEN", "unresolved", {"external": {"category": "mq"}}),
        edge("COBDATFT", "unresolved"),
        edge("SUB", "resolved"),
    ])
    db_session.commit()
    try:
        assert summarize_edges(db_session, source.id) == {
            "by_resolution": {"resolved": 1, "unresolved": 3},
            "unresolved_external": 2,
            "unresolved_open": 1,
            "external_by_category": {"cics": 1, "mq": 1},
        }
    finally:
        db_session.delete(source)
        db_session.commit()
