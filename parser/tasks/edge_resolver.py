"""
parser/tasks/edge_resolver.py
================================
Pass 2 (Plan §6.4, docs/ENTSCHEIDUNGEN.md E-1/E-2): löst globale Kantenarten
(CALL/COPY) über `dst_name` und geerbte Copybook-USES pfadgenau auf, sobald ihr Ziel
existiert — ohne Reparse. Läuft synchron am Ende jedes `GitConnector.sync()`
(kein eigener Celery-Task nötig, es ist ein einzelner beschränkter Query plus
ein paar UPDATEs, kein Hintergrundlauf im Sinne von link_builder.py).

Braucht das nicht nur, weil ein CALL 'B' aus Programm A geparst wird, bevor B
selbst an der Reihe ist (alphabetische/Dateisystem-Reihenfolge) — auch beim
inkrementellen Sync bleibt eine Kante so lange unresolved, bis ihr Ziel zum
ersten Mal geparst wurde, unabhängig davon, wie viele Syncs dazwischen liegen.

Rein programmlokale Kantenarten (PERFORM/GOTO/USES, `scope_entity_id` gesetzt)
sind hier absichtlich außen vor — die sind laut E-1 schon beim Parsen
vollständig auflösbar (parser/cobol_persist.py) und dürfen NIE global über
dst_name gejoint werden (Paragraphen-/Feldnamen wie „INIT-PARA"/„WS-STATUS"
sind in hunderten Programmen gleich benannt).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.database import CodeEdge, CodeEntity

# CALL-Ziele sind Programme, COPY-Ziele sind Copybooks — getrennt statt über
# einen gemeinsamen Namensindex, damit ein Programm und ein gleichnamiges
# Copybook (unwahrscheinlich, aber möglich) sich nicht gegenseitig verdecken.
_TARGET_TYPE_BY_EDGE_TYPE = {"CALL": "program", "COPY": "copybook"}


def resolve_global_edges(db: Session, source_id: int) -> int:
    """Löst offene CALL/COPY- und Copybook-USES-Kanten dieser Quelle auf. Nur bei GENAU
    EINEM Treffer (E-1/E-2 „kein Raten") — ein Namenskonflikt (z.B. zwei
    gleich benannte Programme im selben Repo) bleibt bewusst unresolved statt
    falsch verdrahtet zu werden. Committet selbst, da als letzter Schritt
    eines Syncs aufgerufen. Gibt die Anzahl neu aufgelöster Kanten zurück."""
    candidates = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.resolution == "unresolved",
            CodeEdge.dst_entity_id.is_(None),
            CodeEdge.type.in_((*_TARGET_TYPE_BY_EDGE_TYPE.keys(), "USES")),
        )
        .all()
    )
    if not candidates:
        return 0

    by_type_and_name: dict[str, dict[str, list[CodeEntity]]] = {
        "program": {}, "copybook": {},
    }
    targets = (
        db.query(CodeEntity)
        .filter(CodeEntity.source_id == source_id, CodeEntity.type.in_(("program", "copybook")))
        .all()
    )
    for row in targets:
        by_type_and_name[row.type].setdefault(row.name.upper(), []).append(row)

    resolved = 0
    for edge in candidates:
        if edge.type == "USES":
            meta = edge.meta_json or {}
            target_qname = meta.get("target_qualified_name")
            target_path = meta.get("copybook_path")
            if not target_qname or not target_path:
                continue
            matches = db.query(CodeEntity).filter(
                CodeEntity.source_id == source_id,
                CodeEntity.type == "data_item",
                CodeEntity.file_path == target_path,
                CodeEntity.qualified_name == target_qname,
            ).all()
            if len(matches) == 1:
                edge.dst_entity_id = matches[0].id
                edge.resolution = "resolved"
                resolved += 1
            continue
        target_type = _TARGET_TYPE_BY_EDGE_TYPE[edge.type]
        matches = by_type_and_name[target_type].get(edge.dst_name.upper(), [])
        if len(matches) == 1:
            edge.dst_entity_id = matches[0].id
            edge.resolution = "resolved"
            resolved += 1

    if resolved:
        db.commit()
    return resolved
