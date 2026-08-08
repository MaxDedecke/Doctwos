# `unidecode` (MIT shim, not the upstream PyPI package)

## Warum das hier liegt

`mcp-atlassian` (unser Confluence-/Jira-MCP-Konnektor, siehe
`backend/mcp_client.py`) deklariert `unidecode>=1.3.0` als Pflichtabhängigkeit.
Das echte PyPI-Paket `Unidecode` steht unter **GPL-2.0-or-later** — ein
Copyleft-Verstoß gegen CLAUDE.mds Vorgabe „strikt Open Source, nur
MIT/BSD/Apache-2.0". Vollständige Herleitung, geprüfte Optionen und
Entscheidung: `docs/ENTSCHEIDUNGEN.md` E-7.

`mcp-atlassian` selbst benutzt davon genau eine Funktion
(`mcp_atlassian/jira/users.py::normalize_text()`): Namen/E-Mails vor einem
`casefold()`-Vergleich ASCII-transliterieren, um Jira-Assignees per Anzeigename
fuzzy zu finden (Beispiel aus deren eigenem Docstring: poln. „ł" soll auf „l"
matchen). Das ist die komplette Oberfläche, die reproduziert werden muss — nicht
die vollständigen Transliterationstabellen für jedes Schriftsystem, die das
echte Paket mitbringt.

## Was dieses Paket macht

Ein einziges Modul (`unidecode.py`) mit einer Funktion `unidecode(text) -> str`,
implementiert ausschließlich mit der Python-Stdlib (`unicodedata`, NFKD-Zerlegung
+ ASCII-Encode mit `errors="ignore"`) plus einer kleinen handgeschriebenen
Tabelle für die Buchstaben, die Unicode nicht kompatibilitätszerlegt (ł, ø, đ,
æ, œ — genau die Fälle, die auch im Original-Docstring als Beispiel dienen).
Kein Code aus dem GPL-Paket wurde kopiert, portiert oder eingesehen, um dieses
Modul zu schreiben — nur die öffentlich dokumentierte Ein-/Ausgabe der einen
Funktion, die `mcp-atlassian` aufruft.

**Lizenz:** MIT (siehe `LICENSE` in diesem Verzeichnis).

## Warum das funktioniert (pip-Mechanik)

`pyproject.toml` deklariert `name = "unidecode"` — absichtlich identisch zum
echten Paketnamen. pip löst `mcp-atlassian`s `unidecode>=1.3.0`-Anforderung
gegen **irgendeine** installierte Distribution mit passendem Namen und
passender Version auf, unabhängig von der Quelle. Weil `backend/requirements.txt`
diesen lokalen Pfad referenziert, installiert pip unser Shim und lädt das
echte `Unidecode` von PyPI nie herunter — `mcp-atlassian` selbst bleibt
unverändert und normal upgradebar, kein Fork/Patch nötig.

Die Versionsnummer (`1.3.8+doctus.mit.shim`) erfüllt `>=1.3.0` und trägt
gleichzeitig ein PEP-440-Lokalversions-Suffix, damit `pip list`/`pip show`
sofort zeigen, dass das nicht das Original ist.

## Fidelity-Trade-off (bewusst akzeptiert)

NFKD-Zerlegung deckt die meisten lateinischen Diakritika korrekt ab (é→e,
ñ→n, …) — deckungsgleich mit dem Original. Nicht abgedeckt: Transliteration
für andere Schriftsysteme (Kyrillisch, CJK, Griechisch, Hebräisch, …), die das
echte Paket zusätzlich beherrscht. Betrifft in `mcp-atlassian` ausschließlich
die Jira-Assignee-Namenssuche im MCP-Tool-Calling — nicht Confluence, nicht
das RAG-Indexing (`parser/connectors/confluence.py` nutzt `Unidecode` gar
nicht). Für den DRV-Piloten (deutschsprachiges COBOL-Umfeld) ein
vernachlässigbares Restrisiko, kein Sicherheits-/Kernfunktionsproblem.

## Bei einem `mcp-atlassian`-Versionsbump prüfen

Falls `backend/requirements.txt`s `mcp-atlassian`-Pin je erhöht wird: kurz per
`grep -rn "unidecode" <neue-version>` verifizieren, dass die Nutzung weiterhin
auf `normalize_text()` beschränkt ist (siehe Vorgehen in der
Session-Historie/Memory). Falls eine künftige Version `Unidecode` an mehr
Stellen oder mit anderen Aufrufmustern nutzt, muss dieses Shim entsprechend
erweitert werden.
