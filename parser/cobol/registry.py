"""
parser/cobol/registry.py
=========================
O-077: Dispatch-Registry, über die GitConnector._embed_document eine Sprache
(`doc["extra_meta"]["language"]`) auf ihren Struktur-Parser abbildet, statt der
zuvor hartkodierten `if lang in {"cobol", "copybook"}`-Weiche in
parser/connectors/git.py.

O-079: jeder Eintrag ist ein `ParserEntry` mit einem optionalen
`prepare_source`-Hook -- einer quellenweiten Voranalyse, die (falls gesetzt)
einmal pro Sync läuft, bevor die erste Datei dieser Sprache geparst wird, und
deren Ergebnis GitConnector generisch an jeden `parse()`-Aufruf dieser
Sprache weiterreicht. Vorher rief GitConnector dafür `_build_copybook_index()`
unter festem Namen auf -- eine COBOL-spezifische Voranalyse mitten im sonst
sprachneutralen Connector. GitConnector kennt weder den Hook-Namen noch, was
er tut; er sieht nur `ParserEntry.prepare_source`. COBOL/Copybook teilen sich
denselben Hook (`_prepare_copybook_index`, s. u.), weil beide denselben
quellenweiten Copybook-Index brauchen.

COBOL/Copybook bleiben der einzige echte Eintrag -- das ist bewusst so, siehe
docs/OFFENE_ENTWICKLUNGSPUNKTE.md O-077. Genau so eine pluggbare Mehrsprachen-
Schicht (`parser/languages/`, `PARSER_REGISTRY`) gab es schon einmal und wurde
laut docs/TECH_DEBT_CLEANUP_PLAN.md §1a wieder entfernt, weil sie nie
produktiv befüllt war (CLAUDE.md Prinzip 3, "keine Importierung auf Vorrat").
Diese Registry hier ist deshalb bewusst klein gehalten: kein eigenes Paket,
keine Interfaces über das hinaus, was der eine reale Konsument (COBOL)
braucht. Der Dispatch-Mechanismus selbst ist in
parser/tests/test_git_connector.py mit einem Fake-Eintrag abgesichert.
"""

import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import git_utils
from cobol import copybook
from cobol.copybook import CopybookIndex
from cobol.parse import parse_copybook, parse_program
from core.model import ParseResult


class StructureParser(Protocol):
    """Signatur, die jeder Registry-Eintrag erfüllen muss -- exakt das, was
    parse_program()/parse_copybook() heute schon liefern (chunk_size bei
    parse_copybook hat einen Default, bleibt hier also außen vor)."""

    def __call__(self, text: str, path: str, copybook_index: CopybookIndex | None) -> ParseResult: ...


# (wt, extensions) -> beliebiges Vorlauf-Ergebnis, das per Sync einmal gebaut
# und dann pro Datei an StructureParser weitergereicht wird.
PrepareSourceHook = Callable[[str, dict[str, set[str]]], Any]


@dataclass(frozen=True)
class ParserEntry:
    parse: StructureParser
    prepare_source: PrepareSourceHook | None = None


def _prepare_copybook_index(wt: str, extensions: dict[str, set[str]]) -> CopybookIndex:
    """Pass 0 (Plan §6.4/E-2): quellenweiter Copybook-Index, Name -> Liste
    von Pfaden, ergänzt um die Felddefinitionen jedes lesbaren Copybooks.
    Die Dateinamenauflösung bleibt billig; für E-2 werden Copybook-Inhalte
    zusätzlich einmal in-memory geparst, ohne DB-Schreibzugriff. Läuft bei
    JEDEM Sync über den GESAMTEN Baum, nicht nur über geänderte Dateien: ein
    in diesem Sync geändertes Programm kann ein Copybook COPYen, das selbst
    unverändert (und damit gar nicht Teil des Deltas) ist.

    O-079: das hier ist der `prepare_source`-Hook der Registry-Einträge
    "cobol" und "copybook" -- GitConnector ruft ihn nur noch generisch über
    `ParserEntry.prepare_source` auf, nicht mehr unter diesem Namen."""
    copybook_exts = extensions.get("copybook", set())
    if not copybook_exts:
        return CopybookIndex()
    tracked = git_utils.list_tracked_files(wt)
    index = CopybookIndex()
    for path in tracked:
        if os.path.splitext(path)[1].lower() not in copybook_exts:
            continue
        name = os.path.splitext(os.path.basename(path))[0].upper()
        index.setdefault(name, []).append(path)
        full_path = os.path.join(wt, path)
        try:
            if os.path.getsize(full_path) > git_utils.MAX_READ_BYTES:
                continue
            with open(full_path, "r", errors="ignore") as f:
                parsed = parse_copybook(f.read(git_utils.MAX_READ_BYTES), path)
            index.fields_by_path[path] = [
                {
                    "name": entity.name,
                    "parent": entity.parent_name,
                    "qualified_name": entity.qualified_name,
                    "path": path,
                }
                for entity in parsed.entities
                if entity.type == "data_item"
            ]
            index.copy_edges_by_path[path] = [edge for edge in parsed.edges if edge.type == "COPY"]
        except OSError:
            # Der Namensindex bleibt nutzbar; die XREF-Vererbung für diese
            # einzelne, nicht lesbare Datei entfällt fehlertolerant (F-029).
            continue
    # Erst nachdem alle Copybooks gelesen wurden, lassen sich verschachtelte
    # COPYs eindeutig gegen den vollstaendigen Index aufloesen. Die Rekursion
    # beendet Zyklen fehlertolerant; ein zyklisches Copybook liefert dann nur
    # seine lokal definierten Felder statt den Sync abzubrechen.
    local_fields = {path: list(fields) for path, fields in index.fields_by_path.items()}
    expanded: dict[str, list[dict]] = {}

    def fields_for(path: str, ancestry: set[str]) -> list[dict]:
        if path in expanded:
            return expanded[path]
        result = list(local_fields.get(path, []))
        if path in ancestry:
            return result
        for edge in index.copy_edges_by_path.get(path, []):
            target = copybook.resolve_path(edge.dst_name, (edge.meta or {}).get("library"), index)
            if target is None or target in ancestry:
                continue
            # Die Hilfsinstanz macht die bereits expandierten Ziel-Felder fuer
            # die gemeinsame REPLACING-Logik sichtbar.
            target_index = CopybookIndex(
                index, fields_by_path={target: fields_for(target, ancestry | {path})}
            )
            result.extend(copybook.inherited_fields([edge], target_index))
        expanded[path] = result
        return result

    for path in local_fields:
        index.fields_by_path[path] = fields_for(path, set())
    return index


# lang (Wert aus classify_extension()/spaces["cobol_extensions"]) -> Registry-Eintrag.
STRUCTURE_PARSERS: dict[str, ParserEntry] = {
    "cobol": ParserEntry(parse=parse_program, prepare_source=_prepare_copybook_index),
    "copybook": ParserEntry(parse=parse_copybook, prepare_source=_prepare_copybook_index),
}
