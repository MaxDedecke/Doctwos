"""
O-121: Buildprofil-Vererbung (Quelle -> Pfad/Member -> Buildvariante).
"""

from cobol.profile import BuildProfile, ProfileFragment, resolve_profile


def test_no_fragments_yield_empty_profile_without_diagnostics():
    profile, diagnostics = resolve_profile()
    assert profile == BuildProfile()
    assert diagnostics == []


def test_single_layer_value_is_used_and_attributed():
    profile, diagnostics = resolve_profile(source=ProfileFragment(compiler_family="GNUCOBOL"))
    assert profile.compiler_family == "GNUCOBOL"
    assert profile.resolved_from["compiler_family"] == "source"
    assert diagnostics == []


def test_more_specific_layer_silently_wins_when_less_specific_layer_is_unset():
    profile, diagnostics = resolve_profile(
        source=ProfileFragment(source_format="fixed"),
        variant=ProfileFragment(compiler_family="GNUCOBOL"),
    )
    assert profile.source_format == "fixed"
    assert profile.compiler_family == "GNUCOBOL"
    # Zwei verschiedene Felder, keine Ebene widerspricht der anderen -> kein Konflikt.
    assert diagnostics == []


def test_conflicting_explicit_values_on_the_same_field_are_flagged_but_resolved():
    profile, diagnostics = resolve_profile(
        source=ProfileFragment(source_format="fixed"),
        path=ProfileFragment(source_format="free"),
    )
    assert profile.source_format == "free"  # spezifischere Ebene gewinnt
    assert profile.resolved_from["source_format"] == "path"

    assert len(diagnostics) == 1
    assert diagnostics[0].code == "PROFILE_FIELD_OVERRIDDEN"
    assert diagnostics[0].severity == "info"
    assert "source_format" in diagnostics[0].message


def test_agreeing_values_on_multiple_layers_are_not_a_conflict():
    profile, diagnostics = resolve_profile(
        source=ProfileFragment(source_format="free"),
        variant=ProfileFragment(source_format="free"),
    )
    assert profile.source_format == "free"
    assert diagnostics == []


def test_variant_wins_over_path_wins_over_source_for_the_same_field():
    profile, _ = resolve_profile(
        source=ProfileFragment(compiler_version="1.0"),
        path=ProfileFragment(compiler_version="2.0"),
        variant=ProfileFragment(compiler_version="3.0"),
    )
    assert profile.compiler_version == "3.0"
    assert profile.resolved_from["compiler_version"] == "variant"


def test_defines_are_merged_across_layers_more_specific_key_wins():
    profile, _ = resolve_profile(
        source=ProfileFragment(defines={"DEBUG": "0", "REGION": "DE"}),
        path=ProfileFragment(defines={"DEBUG": "1"}),
    )
    assert profile.defines == {"DEBUG": "1", "REGION": "DE"}


def test_copy_search_order_replaces_entirely_at_the_most_specific_non_empty_layer():
    profile, _ = resolve_profile(
        source=ProfileFragment(copy_search_order=("SRC.LIB1", "SRC.LIB2")),
        path=ProfileFragment(copy_search_order=("PATH.LIB1",)),
    )
    assert profile.copy_search_order == ("PATH.LIB1",)


def test_unknown_compiler_family_is_diagnosed_but_still_set():
    profile, diagnostics = resolve_profile(source=ProfileFragment(compiler_family="ACME-COBOL-9000"))
    assert profile.compiler_family == "ACME-COBOL-9000"
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "PROFILE_UNKNOWN_COMPILER_FAMILY"
    assert diagnostics[0].severity == "warning"


def test_known_compiler_family_is_not_diagnosed():
    _, diagnostics = resolve_profile(source=ProfileFragment(compiler_family="GNUCOBOL"))
    assert diagnostics == []


def test_resolve_profile_is_reproducible_for_the_same_inputs():
    source = ProfileFragment(compiler_family="IBM_ENTERPRISE_COBOL", source_format="fixed")
    path = ProfileFragment(encoding="IBM-1141")

    first = resolve_profile(source=source, path=path)
    second = resolve_profile(source=source, path=path)
    assert first == second
