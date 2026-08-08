"""
Verifies the E-7 fix (docs/ENTSCHEIDUNGEN.md): `mcp-atlassian` requires
`unidecode>=1.3.0`, but the real PyPI package is GPL-2.0-or-later, which
violates CLAUDE.md's "nur MIT/BSD/Apache-2.0" rule. `backend/vendor/
unidecode_shim/` ships a same-named, MIT-licensed replacement so pip never
installs the GPL original — this test guards against a future
`requirements.txt`/Dockerfile edit silently reintroducing it, and against a
version bump breaking the one call site (`mcp_atlassian.jira.users.
normalize_text`) our shim stands in for.
"""
import importlib.metadata

import unidecode as unidecode_module
from unidecode import unidecode


def test_installed_unidecode_is_our_mit_shim_not_the_gpl_original():
    dist = importlib.metadata.distribution("unidecode")
    assert dist.metadata["License"] == "MIT"
    # PEP 440 local version segment we chose specifically so this is
    # unmistakable in `pip list`/`pip show` output too, not just in tests.
    assert "doctus" in dist.version


def test_unidecode_matches_the_real_packages_docstring_example():
    # The exact example from mcp_atlassian.jira.users.normalize_text's
    # docstring ("Polish 'ł' matching ASCII 'l'") — the one behavior
    # mcp-atlassian actually depends on.
    assert unidecode("łódź") == "lodz"


def test_unidecode_folds_common_latin_diacritics_via_nfkd():
    assert unidecode("François") == "Francois"
    assert unidecode("MÜLLER") == "MULLER"


def test_unidecode_handles_empty_and_none_input():
    assert unidecode("") == ""
    assert unidecode_module.unidecode(None) == ""


def test_mcp_atlassian_normalize_text_still_works_against_our_shim():
    """Integration check: mcp-atlassian's own function, unmodified, running
    against our shim instead of the real Unidecode. If a future mcp-atlassian
    version changes how it calls unidecode, this is the test that catches it.
    """
    from mcp_atlassian.jira.users import normalize_text

    assert normalize_text("Łódź") == normalize_text("lodz")
