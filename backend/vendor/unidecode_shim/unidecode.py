"""MIT-licensed shim for the small part of the `Unidecode` API that
`mcp-atlassian` actually uses.

Why this file exists (docs/ENTSCHEIDUNGEN.md E-7): `mcp-atlassian` declares a
hard dependency on PyPI's `Unidecode` package, which is GPL-2.0-or-later —
that violates CLAUDE.md's "nur MIT/BSD/Apache-2.0" rule for Doctus. The only
place `mcp-atlassian` actually calls it is
`mcp_atlassian/jira/users.py::normalize_text()`, which ASCII-transliterates a
name/email before a casefolded equality check, purely to fuzzy-match Jira
assignees by display name (e.g. Polish "ł" should match ASCII "l"). That is
the entire surface we need to reproduce — not the full Unicode transliteration
tables the real package ships for every script (Cyrillic, CJK, Greek, ...).

This module is installed *instead of* the real `Unidecode` distribution (see
backend/requirements.txt and README.md in this directory) — pip resolves
mcp-atlassian's `unidecode>=1.3.0` requirement against this package by name
and never downloads the GPL original.

Fidelity trade-off (accepted, see README.md): `unicodedata`-based NFKD
decomposition handles the vast majority of Latin diacritics (é→e, ñ→n, ...)
correctly, matching real Unidecode's output. A handful of letters have no
compatibility decomposition in Unicode (ł, ø, đ, æ, œ) and are handled via the
small explicit table below instead — the same set the real package's own
docstring uses as its example ("ł" → "l"). Scripts real Unidecode also covers
(Cyrillic, CJK, Greek, Hebrew, ...) are out of scope: this shim only needs to
support the Jira assignee-name-matching use case, not general-purpose
transliteration.
"""

import unicodedata

# Letters whose canonical Unicode decomposition does NOT reduce them to a
# base Latin letter + combining mark, so NFKD alone won't ASCII-fold them.
_EXTRA_FOLDS = {
    "ł": "l", "Ł": "L",
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "ß": "ss",  # str.casefold() already does this; kept for direct callers
}


def unidecode(text: str) -> str:
    """ASCII-transliterates `text`, e.g. "łódź" -> "lodz".

    Matches the one call signature mcp-atlassian uses: a single positional
    string argument, non-generator return value.
    """
    if not text:
        return ""
    folded = "".join(_EXTRA_FOLDS.get(ch, ch) for ch in text)
    normalized = unicodedata.normalize("NFKD", folded)
    return normalized.encode("ascii", "ignore").decode("ascii")
