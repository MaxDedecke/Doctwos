from core.analysis_fingerprint import analysis_fingerprint, profile_payload
from cobol.profile import BuildProfile


def test_fingerprint_is_stable_for_equivalent_mapping_order():
    profile = BuildProfile(defines={"REGION": "DE", "DEBUG": "1"})
    first = analysis_fingerprint(
        source_revision="a" * 40,
        profile=profile,
        grammar_version="grammar-v1",
        libraries={"LIB/B.CPY": "b", "LIB/A.CPY": "a"},
    )
    second = analysis_fingerprint(
        source_revision="a" * 40,
        profile=BuildProfile(defines={"DEBUG": "1", "REGION": "DE"}),
        grammar_version="grammar-v1",
        libraries={"LIB/A.CPY": "a", "LIB/B.CPY": "b"},
    )

    assert first == second
    assert len(first) == 64


def test_fingerprint_changes_for_every_parse_relevant_input():
    base = dict(
        source_revision="a" * 40,
        profile=BuildProfile(source_format="fixed"),
        parser_version="parser-v1",
        grammar_version="grammar-v1",
        libraries={"LIB/COMMON.CPY": "b" * 40},
    )
    fingerprint = analysis_fingerprint(**base)

    assert fingerprint != analysis_fingerprint(**{**base, "source_revision": "c" * 40})
    assert fingerprint != analysis_fingerprint(
        **{**base, "profile": BuildProfile(source_format="free")}
    )
    assert fingerprint != analysis_fingerprint(
        **{**base, "profile": BuildProfile(source_format="fixed", debug_mode=True)}
    )
    assert fingerprint != analysis_fingerprint(**{**base, "parser_version": "parser-v2"})
    assert fingerprint != analysis_fingerprint(**{**base, "grammar_version": "grammar-v2"})
    assert fingerprint != analysis_fingerprint(
        **{**base, "libraries": {"LIB/COMMON.CPY": "d" * 40}}
    )


def test_empty_profile_has_an_explicit_stable_payload():
    assert profile_payload(None) == {
        "compiler_family": None,
        "compiler_version": None,
        "source_format": None,
        "source_columns": None,
        "encoding": None,
        "debug_mode": False,
        "defines": {},
        "copy_search_order": [],
        "resolved_from": {},
    }
