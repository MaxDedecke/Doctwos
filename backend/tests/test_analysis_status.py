"""O-120: `core.analysis_status.load_analysis_status()` -- der gemeinsame
Batch-Lookup, den Chat-Zitate, Callgraph und der Wissensquellen-Dateibaum
gleichermaßen benutzen, um SourceScanFile.parse_status durchzureichen."""

from core.analysis_status import load_analysis_status
from models.database import KnowledgeSource, SourceScanFile


def _make_source(db_session, test_project, test_team, name="src"):
    source = KnowledgeSource(project_id=test_project, team_id=test_team, type="Git", name=name)
    db_session.add(source)
    db_session.commit()
    return source


def test_returns_empty_dict_for_empty_keys(db_session):
    assert load_analysis_status(db_session, set()) == {}


def test_ignores_pairs_with_none_source_id_or_path(db_session):
    assert load_analysis_status(db_session, {(None, "a.cbl"), (1, None)}) == {}


def test_looks_up_a_non_complete_status(db_session, test_project, test_team):
    source = _make_source(db_session, test_project, test_team)
    db_session.add(
        SourceScanFile(
            source_id=source.id,
            file_path="PAYROLL.cbl",
            content_hash="abc",
            parse_status="partial",
            parse_error="mismatched input; unbekannte compiler_family",
        )
    )
    db_session.commit()

    result = load_analysis_status(db_session, {(source.id, "PAYROLL.cbl")})

    assert result == {
        (source.id, "PAYROLL.cbl"): {
            "status": "partial",
            "reasons": ["mismatched input", "unbekannte compiler_family"],
        }
    }


def test_complete_status_row_is_filtered_out(db_session, test_project, test_team):
    # Die Mehrheit der Dateien ist "complete" und soll gerade NICHT im
    # Ergebnis auftauchen -- Aufrufer werten "kein Eintrag" bereits als
    # "kein Makel bekannt" (genauso wie parse_status IS NULL).
    source = _make_source(db_session, test_project, test_team)
    db_session.add(
        SourceScanFile(
            source_id=source.id, file_path="OK.cbl", content_hash="abc", parse_status="complete"
        )
    )
    db_session.commit()

    assert load_analysis_status(db_session, {(source.id, "OK.cbl")}) == {}


def test_row_without_reasons_gets_an_empty_reason_list(db_session, test_project, test_team):
    source = _make_source(db_session, test_project, test_team)
    db_session.add(
        SourceScanFile(
            source_id=source.id,
            file_path="BIN.dat",
            content_hash="abc",
            parse_status="skipped",
            parse_error=None,
        )
    )
    db_session.commit()

    result = load_analysis_status(db_session, {(source.id, "BIN.dat")})
    assert result[(source.id, "BIN.dat")] == {"status": "skipped", "reasons": []}


def test_only_requested_keys_are_returned_even_when_the_source_has_more_rows(
    db_session, test_project, test_team
):
    source = _make_source(db_session, test_project, test_team)
    db_session.add_all(
        [
            SourceScanFile(
                source_id=source.id, file_path="A.cbl", content_hash="a", parse_status="partial"
            ),
            SourceScanFile(
                source_id=source.id, file_path="B.cbl", content_hash="b", parse_status="skipped"
            ),
        ]
    )
    db_session.commit()

    result = load_analysis_status(db_session, {(source.id, "A.cbl")})
    assert set(result.keys()) == {(source.id, "A.cbl")}
