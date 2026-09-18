"""
parser/structure_persist.py
=========================
Pass 1 (Plan §6.4, docs/ENTSCHEIDUNGEN.md E-6): schreibt ein `ParseResult`
aus jedem registrierten Strukturparser (rein in-memory, kein DB-Zugriff) für
**eine** Datei nach `code_entities`/`code_edges`. Bewusst außerhalb der
sprachspezifischen Parserpakete — COBOL, Java, Maven, XSLT und XML verwenden
denselben Persistenzvertrag.

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

Kanten dieser Datei werden dagegen vollständig ersetzt —
anders als bei Entities gibt es keine Fremdreferenz von außen auf eine
einzelne Kantenzeile.

Globale Kantenarten bleiben hier unresolved/dynamic — ihre Auflösung ist Pass 2
(parser/tasks/edge_resolver.py), weil das Ziel typischerweise in einer anderen,
möglicherweise noch nicht geparsten Datei liegt. Sprachspezifische lokale
Kanten dürfen dagegen bereits beim Parsen verdrahtet werden.

Wichtig für COBOL-COPY: `copybook.py` setzt `ParsedEdge.resolution="resolved"`
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

from core.model import ParsedEdge, ParseResult
from models.database import CodeEdge, CodeEntity
from link_dirty import enqueue_dirty_item


def _result_language(result: ParseResult) -> str | None:
    """Return the parser language without making persistence parser-specific."""
    for entity in result.entities:
        language = (entity.meta or {}).get("language")
        if language:
            return language
    root_type = result.entities[0].type if result.entities else None
    return {
        "program": "cobol",
        "copybook": "copybook",
    }.get(root_type)


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
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == file_path,
            CodeEntity.variant_key == result.variant_key,
        )
        .all()
    }

    # Java package entities are shared by all files in a package, while the
    # historical COBOL entities are file-owned.  The DB key is intentionally
    # source/variant/QName (not source/file/QName), so reuse an already
    # persisted QName when a second file contributes to the same package.
    # Keeping the lookup here also makes the generic persistence contract
    # explicit for future structure parsers.
    for entity in result.entities:
        qname = entity.qualified_name or entity.name
        if qname in existing:
            continue
        # Only Java package/module containers are intentionally shared across
        # files.  A class QName such as ``com.example.App`` is *not* globally
        # unique in a Maven multi-module source tree; sharing it would merge
        # same-named classes from independent modules.
        share_container = (
            (ent.meta or {}).get("language") == "java"
            and ent.type in {"package", "module"}
        )
        shared = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.source_id == source_id,
                CodeEntity.variant_key == result.variant_key,
                CodeEntity.qualified_name == qname,
            )
            .first()
            if share_container
            else None
        )
        if shared is not None:
            existing[qname] = shared

    by_qname: dict[str, CodeEntity] = {}
    seen_qnames: set[str] = set()

    for ent in result.entities:
        qname = ent.qualified_name or ent.name
        seen_qnames.add(qname)
        row = existing.get(qname)
        was_new = row is None
        previous_hash = row.content_hash if row is not None else None
        if row is None:
            row = CodeEntity(
                source_id=source_id,
                project_id=project_id,
                file_path=file_path,
                variant_key=result.variant_key,
            )
            db.add(row)
        owns_row = row.file_path in {None, file_path}
        if owns_row:
            row.name = ent.name
            row.type = ent.type
            row.qualified_name = qname
            # Shared Java package/module rows keep their first owning file. A
            # newly created row already carries this file path below.
            row.file_path = file_path
            row.start_line = ent.start_line
            row.end_line = ent.end_line
            row.meta_json = ent.meta or None
            row.content_hash = content_hash
            if was_new or previous_hash != content_hash:
                row.link_revision = (row.link_revision or 0) + 1
            if not (ent.meta.get("language") == "java" and ent.type in {"package", "module"}):
                row.parent_id = _parent_id(
                    qname,
                    by_qname,
                    existing,
                    parent_qualified_name=ent.parent_qualified_name,
                    legacy_parent_name=ent.parent_name,
                )
        elif ent.meta.get("language") == "java" and ent.type in {"package", "module"}:
            # Java packages/modules are shared by files. They must not retain
            # the compilation unit of whichever file created the row first,
            # because deleting that file would cascade through the shared
            # container into unchanged files.
            row.parent_id = None
        # Sofort flushen, damit die eigene id für Kinder verfügbar ist, die
        # in derselben Schleife noch folgen (entities sind laut parse.py
        # immer in Eltern-vor-Kind-Reihenfolge aufgebaut).
        db.flush()
        by_qname[qname] = row
        if project_id is not None and (was_new or previous_hash != content_hash):
            enqueue_dirty_item(
                db,
                project_id=project_id,
                entity_id=row.id,
                reason="content_changed" if not was_new else "entity_added",
            )

    stale_qnames = set(existing) - seen_qnames
    if stale_qnames:
        db.query(CodeEntity).filter(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == file_path,
            CodeEntity.variant_key == result.variant_key,
            CodeEntity.qualified_name.in_(stale_qnames),
        ).delete(synchronize_session=False)

    by_name: dict[str, list[CodeEntity]] = {}
    for row in by_qname.values():
        by_name.setdefault(row.name.upper(), []).append(row)

    # A shared Java package entity can be referenced by several source files.
    # Only delete edges whose source entity is owned by this file; otherwise a
    # reparse of file B would delete imports/relations persisted for file A.
    file_entity_ids = [row.id for row in by_qname.values() if row.file_path == file_path]
    if file_entity_ids:
        db.query(CodeEdge).filter(
            CodeEdge.source_id == source_id,
            CodeEdge.variant_key == result.variant_key,
            CodeEdge.src_entity_id.in_(file_entity_ids),
        ).delete(synchronize_session=False)

    edge_count = 0
    language = _result_language(result)
    for edge in result.edges:
        row = _build_edge(
            project_id,
            source_id,
            result.variant_key,
            edge,
            by_qname,
            by_name,
            language=language,
        )
        if row is None:
            continue
        db.add(row)
        edge_count += 1

    db.flush()
    return {"entities": len(by_qname), "edges": edge_count}


def _parent_id(
    qname: str,
    by_qname: dict[str, CodeEntity],
    existing: dict[str, CodeEntity],
    *,
    parent_qualified_name: str | None = None,
    legacy_parent_name: str | None = None,
) -> int | None:
    """Resolve the explicit parent, retaining the old QName split only for
    ParseResults created before ``parent_qualified_name`` was introduced."""
    if parent_qualified_name is None:
        # A missing explicit parent on a root is intentional, even when its
        # QName contains dots (for example a Java package or source path).
        # Only older child entities with a parent_name use the old split.
        if legacy_parent_name is None or "." not in qname:
            return None
        parent_qualified_name = qname.rsplit(".", 1)[0]
    row = by_qname.get(parent_qualified_name) or existing.get(parent_qualified_name)
    return row.id if row else None


def _find_src(
    edge: ParsedEdge,
    by_qname: dict[str, CodeEntity],
    by_name: dict[str, list[CodeEntity]],
    *,
    language: str | None = None,
) -> CodeEntity | None:
    """Find an edge source using a qualified identity where available.

    COBOL's simple-name/program-scope fallback is delegated to its own policy
    module. Other languages must provide a stable qualified source name or an
    unambiguous simple-name match.
    """
    direct = by_qname.get(edge.src_name)
    if direct is not None:
        return direct
    source_qname = (edge.meta or {}).get("source_qualified_name")
    if source_qname:
        direct = by_qname.get(source_qname)
        if direct is not None:
            return direct
    if language in {"cobol", "copybook"} or edge.scope is not None:
        from cobol.persistence import find_source

        return find_source(edge, by_qname, by_name)
    candidates = by_name.get(edge.src_name.upper(), []) if edge.src_name else []
    return candidates[0] if len(candidates) == 1 else None


def _build_edge(
    project_id: int | None,
    source_id: int,
    variant_key: str,
    edge: ParsedEdge,
    by_qname: dict[str, CodeEntity],
    by_name: dict[str, list[CodeEntity]],
    *,
    language: str | None = None,
) -> CodeEdge | None:
    language = language or (edge.meta or {}).get("language")
    src = _find_src(edge, by_qname, by_name, language=language)
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
            from cobol.persistence import resolve_local_target

            dst_entity = resolve_local_target(edge, by_qname, by_name)
            if dst_entity is None:
                resolution = "unresolved"
    elif (edge.meta or {}).get("language") in {"java", "xslt", "jsp", "html", "shell"}:
        # Java and XSLT have no COBOL-style scope column.  Local resolution is
        # represented by a stable target QName in edge metadata.  Only mark a
        # DB edge resolved once its target row is actually present; the
        # language-specific/global resolver fills cross-file targets later.
        target_qname = (edge.meta or {}).get("target_qualified_name")
        if resolution == "resolved" and target_qname:
            dst_entity = by_qname.get(target_qname)
            if dst_entity is None:
                resolution = "unresolved"
        elif resolution == "resolved":
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
        variant_key=variant_key,
        meta_json=edge.meta or None,
    )
