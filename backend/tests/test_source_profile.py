import pytest

from core.build_profile import (
    ProfileValidationError,
    validate_build_profile,
    validate_language_paths,
)
from core.source_preflight import parser_gaps
from models.database import SourceScanFile
from tests.test_knowledge_sources import make_project  # noqa: F401  (fixture)


def test_build_profile_is_normalized_to_source_and_paths():
    profile = validate_build_profile(
        {
            "compiler_family": "IBM_ENTERPRISE_COBOL",
            "source_format": "fixed",
            "encoding": "CCSID-273",
            "defines": {"DEBUG": 1},
            "copy_search_order": ["/copylib/prod/", "copylib/common"],
        }
    )
    assert profile["source"]["defines"] == {"DEBUG": "1"}
    assert profile["source"]["copy_search_order"] == ["copylib/prod", "copylib/common"]
    assert profile["paths"] == {}


def test_path_overrides_are_validated_like_the_source_fragment():
    profile = validate_build_profile(
        {"source": {"source_format": "fixed"}, "paths": {"/free/": {"source_format": "free"}}}
    )
    assert profile["paths"] == {"free": {"source_format": "free"}}


@pytest.mark.parametrize(
    "bad",
    [
        {"source_format": "wide"},
        {"encoding": "CCSID-99999999"},
        {"debug_mode": "yes"},
        {"literal_delimiter": "backtick"},
        {"typo_field": 1},
        {"source_columns": {"sequence_end": 9, "indicator_column": 7}},
        {"copy_search_order": []},
        {"defines": {"": "x"}},
    ],
)
def test_invalid_profile_values_are_rejected_with_a_message(bad):
    with pytest.raises(ProfileValidationError):
        validate_build_profile(bad)


def test_language_paths_accept_only_known_languages_and_safe_prefixes():
    assert validate_language_paths({"/COBOL/": "cobol", "COPYLIB": "copybook"}) == {
        "COBOL": "cobol",
        "COPYLIB": "copybook",
    }
    with pytest.raises(ProfileValidationError):
        validate_language_paths({"src": "python"})
    with pytest.raises(ProfileValidationError):
        validate_language_paths({"../etc": "cobol"})


def test_parser_gaps_rank_patterns_by_occurrences_and_cite_an_example():
    error = (
        "mismatched input 'GENERATE' expecting SECTION (insgesamt 3x, Zeilen: 18, 19, 23); "
        "mismatched input 'FROM' expecting SECTION"
    )
    rows = [
        ("a/PGM1.cbl", "partial", error),
        ("a/PGM2.cbl", "partial", "mismatched input 'GENERATE' expecting SECTION"),
        ("a/PGM3.cbl", "complete", None),
    ]

    gaps = parser_gaps(rows)

    assert gaps[0] == {
        "pattern": "mismatched input 'GENERATE'",
        "occurrences": 4,
        "files": 2,
        "example": "a/PGM1.cbl:18",
    }
    assert gaps[1]["pattern"] == "mismatched input 'FROM'"


def _git_source(client, project_id):
    response = client.post(
        "/knowledge-sources", json={"name": "git-source", "type": "Git", "project_id": project_id}
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def test_profile_round_trip_and_validation_errors(client, make_project):  # noqa: F811
    source_id = _git_source(client, make_project())

    saved = client.put(
        f"/knowledge-sources/{source_id}/build-profile",
        json={
            "build_profile": {"source_format": "free", "encoding": "cp1252"},
            "language_paths": {"COBOL": "cobol"},
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["build_profile"]["source"]["source_format"] == "free"

    loaded = client.get(f"/knowledge-sources/{source_id}/build-profile").json()
    assert loaded["language_paths"] == {"COBOL": "cobol"}

    rejected = client.put(
        f"/knowledge-sources/{source_id}/build-profile",
        json={"build_profile": {"source_format": "wide"}},
    )
    assert rejected.status_code == 422

    cleared = client.put(
        f"/knowledge-sources/{source_id}/build-profile", json={"build_profile": None}
    )
    assert cleared.json()["build_profile"] is None
    assert cleared.json()["language_paths"] == {"COBOL": "cobol"}


def test_preflight_reports_gaps_encodings_and_missing_profile(
    client,
    make_project,  # noqa: F811
    db_session,
):
    source_id = _git_source(client, make_project())
    db_session.add_all(
        [
            SourceScanFile(
                source_id=source_id,
                file_path="COBOL/PGM1.cbl",
                content_hash="1",
                language="cobol",
                parse_status="partial",
                parse_error="mismatched input 'GENERATE' expecting SECTION",
                encoding="cp1252",
            ),
            SourceScanFile(
                source_id=source_id,
                file_path="export/MEMBER",
                content_hash="2",
                language="text",
                parse_status="text_fallback",
            ),
        ]
    )
    db_session.commit()

    report = client.get(f"/knowledge-sources/{source_id}/preflight").json()

    assert report["files"]["by_language"]["cobol"] == {"partial": 1}
    assert report["files"]["encodings"] == {"cp1252": 1}
    assert report["parser_gaps"][0]["pattern"] == "mismatched input 'GENERATE'"
    codes = {hint["code"] for hint in report["hints"]}
    assert {"PROFILE_MISSING", "ENCODING_FALLBACK", "EXTENSIONLESS_AS_TEXT", "PARSER_GAPS"} <= codes


def test_profile_endpoints_reject_non_git_sources(client, make_project):  # noqa: F811
    response = client.post(
        "/knowledge-sources",
        json={"name": "wiki", "type": "Confluence", "project_id": make_project()},
    )
    source_id = response.json()["id"]

    assert client.get(f"/knowledge-sources/{source_id}/preflight").status_code == 400
