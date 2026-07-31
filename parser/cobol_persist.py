"""
parser/cobol_persist.py
=========================
Pass 1 (Plan §6.4, docs/ENTSCHEIDUNGEN.md E-6): schreibt ein `ParseResult`
(`cobol.parse.parse_program()`/`parse_copybook()`, rein in-memory, kein
DB-Zugriff) für **eine** Datei nach `code_entities`/`code_edges`. Bewusst
außerhalb von `parser/cobol/` — dieses Paket bleibt komplett DB-frei (E-6),
genau wie `chunk_reindex.py` neben dem generischen `code_parser.py` sitzt.

Zentrale Entwurfsentscheidung: Entities werden per (source_id, file_path,
qualified_name) UPSERT geschrieben, nicht gelöscht+neu eingefügt. Ein Reparse
(geänderte Datei) würde sonst über CodeEdge.dst_entity_id/scope_entity_id
(beide ON DELETE CASCADE) auch Kanten aus UNVERÄNDERTEN anderen Dateien
mitreißen, die auf eine Entity dieser Datei zeigen (z.B. ein CALL aus
Programm C auf ein Programm A, das gerade reindexiert wird) — obwohl C in
diesem Sync gar nicht neu geparst wird (Resume-Skip über content_hash) und
die Kante deshalb bis zum nächsten vollständigen Sync von C verloren bliebe.
Nur wirklich verschwundene Entities (z.B. ein gelöschter Paragraph) werden
gezielt per qualified_name entfernt — CASCADE greift dann zu Recht.

Kanten dieser Datei (src liegt laut Konstruktion in procedure.py/copybook.py/
sql.py/xref.py immer in derselben Datei) werden dagegen vollständig ersetzt —
anders als bei Entities gibt es keine Fremdreferenz von außen auf eine
einzelne Kantenzeile.

Globale Kantenarten (CALL/COPY, scope=None) bleiben hier unresolved/dynamic —
ihre Auflösung ist Pass 2 (parser/tasks/edge_resolver.py), weil das Ziel
typischerweise in einer anderen, möglicherweise noch nicht geparsten Datei
liegt. Lokale Kantenarten (PERFORM/GOTO/USES, scope gesetzt) sind laut E-1
schon beim Parsen vollständig auflösbar und werden hier sofort verdrahtet.

Wichtig für COPY: `copybook.py` setzt `ParsedEdge.resolution="resolved"`
bereits, sobald der Pass-0-Namensindex GENAU EINEN Pfad zu `dst_name` kennt —
das ist eine reine Namensauflösung zur Parse-Zeit, keine DB-Auflösung (die
Ziel-Entity existiert zu diesem Zeitpunkt evtl. noch gar nicht in
`code_entities`). `_build_edge()` erzwingt deshalb für alle globalen Kanten
`resolution="unresolved"` (außer `"dynamic"`) unabhängig davon, was der
Parser meldet — DB-seitig gilt "resolved" erst, wenn Pass 2 tatsächlich eine
Entity gefunden und `dst_entity_id` gesetzt hat. Ohne diese Umwertung würde
Pass 2s `WHERE resolution = 'unresolved'`-Filter eine schon "resolved"
markierte, aber nie verlinkte COPY-Kante für immer überspringen — genau
dieser Bug fiel beim Schreiben von test_ap4_persistence.py auf.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from cobol.model import ParsedEdge, ParseResult
from models.database import CodeEdge, CodeEntity

# Welche Entity-Typen als Ziel einer lokalen Kantenart infrage kommen —
# verhindert z.B., dass ein Datenfeld fälschlich als PERFORM-Ziel durchgeht,
# nur weil es zufällig denselben Namen wie ein Paragraph trägt.
_LOCAL_TARGET_TYPES: dict[str, tuple[str, ...]] = {
    "PERFORM": ("paragraph", "section"),
    "GOTO": ("paragraph", "section"),
    "USES": ("data_item",),
    "DEFINES": ("data_item",),
}

# Plausible Herkunftstypen einer Kante, je Kantenart — grenzt den Bereich
# beim Auflösen von edge.src_name (Paragraph-/Programmname oder ein
# synthetischer SQL-Block-Name) ein.
_SRC_TYPES: dict[str, tuple[str, ...]] = {
    "CALL": ("program", "paragraph"),
    "PERFORM": ("program", "paragraph"),
    "GOTO": ("program", "paragraph"),
    "COPY": ("program", "paragraph"),
    "USES": ("program", "paragraph", "sql_block"),
}


def persist_parse_result(
    db: Session,
    *,
    project_id: int | None,
    source_id: int,
    file_path: str,
    content_hash: str,
    result: ParseResult,
) -> dict[str, int]:
    """Schreibt Entities und Kanten von `result` für `file_path`. Muss nach
    einem etwaigen vorherigen Aufruf für dieselbe Datei erneut aufgerufen
    werden können (Reparse bei geänderter Datei) — daher UPSERT statt reinem
    INSERT. Committet nicht selbst; der Aufrufer (Connector) entscheidet den
    Transaktionsrahmen (siehe GitConnector._save_document_chunks)."""

    existing = {
        row.qualified_name: row
        for row in db.query(CodeEntity)
        .filter(CodeEntity.source_id == source_id, CodeEntity.file_path == file_path)
        .all()
    }

    by_qname: dict[str, CodeEntity] = {}
    seen_qnames: set[str] = set()

    for ent in result.entities:
        qname = ent.qualified_name or ent.name
        seen_qnames.add(qname)
        row = existing.get(qname)
        if row is None:
            row = CodeEntity(source_id=source_id, project_id=project_id, file_path=file_path)
            db.add(row)
        row.name = ent.name
        row.type = ent.type
        row.qualified_name = qname
        row.start_line = ent.start_line
        row.end_line = ent.end_line
        row.meta_json = ent.meta or None
        row.content_hash = content_hash
        row.parent_id = _parent_id(qname, by_qname, existing)
        # Sofort flushen, damit die eigene id für Kinder verfügbar ist, die
        # in derselben Schleife noch folgen (entities sind laut parse.py
        # immer in Eltern-vor-Kind-Reihenfolge aufgebaut).
        db.flush()
        by_qname[qname] = row

    stale_qnames = set(existing) - seen_qnames
    if stale_qnames:
        db.query(CodeEntity).filter(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == file_path,
            CodeEntity.qualified_name.in_(stale_qnames),
        ).delete(synchronize_session=False)

    by_name: dict[str, list[CodeEntity]] = {}
    for row in by_qname.values():
        by_name.setdefault(row.name.upper(), []).append(row)

    file_entity_ids = [row.id for row in by_qname.values()]
    if file_entity_ids:
        db.query(CodeEdge).filter(
            CodeEdge.source_id == source_id,
            CodeEdge.src_entity_id.in_(file_entity_ids),
        ).delete(synchronize_session=False)

    edge_count = 0
    for edge in result.edges:
        row = _build_edge(project_id, source_id, edge, by_qname, by_name)
        if row is None:
            continue
        db.add(row)
        edge_count += 1

    db.flush()
    return {"entities": len(by_qname), "edges": edge_count}


def _parent_id(
    qname: str, by_qname: dict[str, CodeEntity], existing: dict[str, CodeEntity]
) -> int | None:
    """Der Elternteil einer Entity ist immer der qualified_name minus des
    eigenen letzten Namenssegments — qualified_name wird in parse.py
    ausschließlich über `f"{parent_qname}.{name}"` gebaut (_qualify()), ein
    String-Split reicht deshalb, ganz ohne die namensbasierte Mehrdeutigkeit,
    die eine Suche über parent_name (nur ein Klartextname, kein Namensraum)
    hätte."""
    if "." not in qname:
        return None
    parent_qname = qname.rsplit(".", 1)[0]
    row = by_qname.get(parent_qname) or existing.get(parent_qname)
    return row.id if row else None


def _find_src(
    edge: ParsedEdge, by_qname: dict[str, CodeEntity], by_name: dict[str, list[CodeEntity]]
) -> CodeEntity | None:
    if not edge.src_name:
        # procedure.py/xref.py liefern "" als src_name, wenn eine Anweisung
        # direkt unter PROCEDURE DIVISION ohne umschließenden Paragraphen
        # steht (seltener, aber gültiger Fall) - die Quelle ist dann das
        # Programm selbst.
        return next((row for row in by_qname.values() if row.type == "program"), None)

    allowed = _SRC_TYPES.get(edge.type)
    candidates = [c for c in by_name.get(edge.src_name.upper(), []) if allowed is None or c.type in allowed]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # Anders als bei der Zielauflösung (E-2 "kein Raten") geht es hier nur
        # um die Herkunft einer bereits geparsten Kante, nicht um eine neue
        # fachliche Aussage - eine Namenskollision am Quellknoten (z.B. zwei
        # gleichnamige Paragraphen in unterschiedlichen Sections) ist ein
        # seltener Randfall, der Sicht auf die Kante nicht verlieren soll.
        return candidates[0]
    return None


def _resolve_local_target(
    edge: ParsedEdge, by_qname: dict[str, CodeEntity], by_name: dict[str, list[CodeEntity]]
) -> CodeEntity | None:
    allowed = _LOCAL_TARGET_TYPES.get(edge.type)
    candidates = [c for c in by_name.get(edge.dst_name.upper(), []) if allowed is None or c.type in allowed]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        parent_hint = (edge.meta or {}).get("parent")
        if parent_hint:
            narrowed = [c for c in candidates if (_parent_name(c, by_qname) or "").upper() == parent_hint.upper()]
            if len(narrowed) == 1:
                return narrowed[0]
    return None


def _parent_name(row: CodeEntity, by_qname: dict[str, CodeEntity]) -> str | None:
    if not row.qualified_name or "." not in row.qualified_name:
        return None
    parent = by_qname.get(row.qualified_name.rsplit(".", 1)[0])
    return parent.name if parent else None


def _build_edge(
    project_id: int | None,
    source_id: int,
    edge: ParsedEdge,
    by_qname: dict[str, CodeEntity],
    by_name: dict[str, list[CodeEntity]],
) -> CodeEdge | None:
    src = _find_src(edge, by_qname, by_name)
    if src is None:
        # Inkonsistenz zwischen Parser-Modul und Entity-Bau (sollte nicht
        # vorkommen) - kein Abbruch (Plan §6.1 Regel 2), die Kante wird
        # schlicht ausgelassen statt mit einer erfundenen Quelle gespeichert.
        return None

    dst_entity: CodeEntity | None = None
    resolution = edge.resolution
    scope_entity_id: int | None = None

    if edge.scope is not None:
        scope_row = by_qname.get(edge.scope)
        scope_entity_id = scope_row.id if scope_row else None
        if resolution == "resolved" and (edge.meta or {}).get("target_qualified_name"):
            # E-2-COPY-XREF: Ziel liegt absichtlich in einer anderen Datei
            # und wird nach dem vollständigen Sync pfadgenau nachaufgelöst.
            resolution = "unresolved"
        elif resolution == "resolved":
            dst_entity = _resolve_local_target(edge, by_qname, by_name)
            if dst_entity is None:
                resolution = "unresolved"
    else:
        # Global (CALL/COPY): copybook.py setzt "resolved" schon zur
        # Parse-Zeit, sobald der Pass-0-Namensindex GENAU EINEN Pfad zu
        # dst_name kennt - das ist eine reine Namensauflösung, keine
        # DB-Auflösung, die Ziel-Entity existiert zu diesem Zeitpunkt evtl.
        # noch gar nicht in code_entities. "resolved" darf hier erst gelten,
        # sobald Pass 2 (edge_resolver.py) tatsächlich eine Entity gefunden
        # UND dst_entity_id gesetzt hat - sonst filtert dessen
        # `resolution == "unresolved"`-Bedingung die Kante fälschlich heraus
        # und sie bleibt für immer unverlinkt trotz "resolved"-Status
        # (gefunden über test_ap4_persistence.py). "dynamic" (CALL über eine
        # Variable) ist die einzige Ausnahme, die nie auflösbar wird.
        resolution = "dynamic" if edge.resolution == "dynamic" else "unresolved"

    return CodeEdge(
        project_id=project_id,
        source_id=source_id,
        src_entity_id=src.id,
        dst_entity_id=dst_entity.id if dst_entity is not None else None,
        dst_name=edge.dst_name,
        type=edge.type,
        resolution=resolution,
        scope_entity_id=scope_entity_id,
        src_start_line=edge.src_start_line,
        src_end_line=edge.src_end_line,
        meta_json=edge.meta or None,
    )
