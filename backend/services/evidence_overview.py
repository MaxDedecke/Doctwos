"""Projektüberblick als Baustein des Belegpakets (``answer_context``).

Für Fragen ohne benanntes Symbol („Was ist das für ein Projekt?“, „Welche Prozesse gibt es?“) gab es bisher
nichts Passendes; der Chat lud dann die ersten 20 Entitäten einer einzelnen Datei. Der Überblick kommt
vollständig aus dem Index: Dokumentation an der Wurzel, Bestand je Sprache, Verzeichnisse mit den meisten
Einheiten, Einstiege und meistgenutzte Einheiten.

Sprachunabhängig: gelesen werden nur Rollen aus dem ``LanguageProfile`` und die vorberechneten Dateikanten
(``code_file_edges``). Jede Angabe trägt ``cite``; was der Index nicht hergibt, steht als Lücke in ``gaps``.
"""

import json
import re
from collections import Counter

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session, aliased

from codena_models.database import CodeEdge, CodeEntity, CodeFileEdge, DocumentChunk
from codena_models.language_profile import CONTAINER_TYPES, CONTROL_EDGES, PROFILES, profile_of
from services.call_flow import TEST_PATH_PATTERN

OVERVIEW_INTENT = re.compile(
    r"was (ist|macht|tut) (das|dies\w*|die|der) .{0,30}(projekt|system|anwendung|codebase|code ?basis|repo\w*|bestand)"
    r"|worum geht|überblick|ueberblick|übersicht|uebersicht|architektur|\baufbau\b|wie ist .{0,40}(aufgebaut|strukturiert)"
    r"|explor\w+|\btour\b|rundgang|onboarding|einstieg|welche (prozesse|programme|module|komponenten|abläufe|ablaeufe|jobs)"
    r"|overview|what (is|does) (this|the) (project|system|code ?base|repo\w*)|how is .{0,40} (structured|organi[sz]ed)"
    r"|which (programs|modules|components|processes|jobs)",
    re.IGNORECASE,
)

# Dokumentation an der Wurzel; exakte Pfade, damit die Abfrage den Pfadindex nutzt statt Abschnitte zu scannen.
_ROOT_DOCUMENTS = ("README.md", "README", "README.txt", "README.rst", "README.adoc", "readme.md")
_DOCUMENT_CHARS = 1400
_AREAS = 8
_AREA_DEPTH = 4
_ENTRY_POINTS = 12
_CENTRAL_UNITS = 12
_NAMED_TARGETS = 4
# Kandidaten, die bei unvollständig gespeicherten Dateikanten gegen die Einzelkanten geprüft werden.
_ENTRY_CANDIDATES = 40


def _control_file_edge(edge) -> object:
    """Dateikante, die mindestens eine Kontrollfluss-Kante trägt (``edge_types`` ist eine JSON-Liste)."""
    types = cast(edge.edge_types, String)
    return or_(*(types.like(f'%"{name}"%') for name in sorted(CONTROL_EDGES)))


def _documentation(db: Session, project_id: int) -> list[dict]:
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.project_id == project_id, DocumentChunk.file_path.in_(_ROOT_DOCUMENTS)
        )
        .order_by(DocumentChunk.file_path, DocumentChunk.start_line.asc().nullsfirst())
        .limit(6)
        .all()
    )
    documents: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.file_path in seen or not (chunk.content or "").strip():
            continue
        seen.add(chunk.file_path)
        start = chunk.start_line or 1
        documents.append(
            {
                "file": chunk.file_path,
                "cite": f"{chunk.file_path}:{start}",
                "lines": [start, chunk.end_line or start],
                "excerpt": chunk.content.strip()[:_DOCUMENT_CHARS],
            }
        )
    return documents[:2]


def _inventory(db: Session, project_id: int) -> list[dict]:
    counts = dict(
        db.query(CodeEntity.type, func.count())
        .filter(CodeEntity.project_id == project_id)
        .group_by(CodeEntity.type)
        .all()
    )
    inventory = []
    for profile in PROFILES:
        row = {
            "language": profile.name,
            "containers": {t: counts[t] for t in sorted(profile.containers) if counts.get(t)},
            "routines": sum(counts.get(t, 0) for t in profile.routines),
            "data": sum(counts.get(t, 0) for t in profile.data),
        }
        if row["containers"] or row["routines"] or row["data"]:
            inventory.append(row)
    return inventory


def _areas(db: Session, project_id: int) -> list[dict]:
    """Verzeichnisse mit den meisten Einheiten; tiefe Paketpfade werden auf wenige Ebenen zusammengefasst."""
    directory = func.regexp_replace(CodeEntity.file_path, "/[^/]*$", "")
    rows = (
        db.query(directory, func.count())
        .filter(
            CodeEntity.project_id == project_id,
            CodeEntity.type.in_(CONTAINER_TYPES),
            ~CodeEntity.file_path.op("~")(TEST_PATH_PATTERN),
        )
        .group_by(directory)
        .all()
    )
    totals: Counter[str] = Counter()
    for path, count in rows:
        totals["/".join((path or "").split("/")[:_AREA_DEPTH]) or "."] += count
    return [{"directory": path, "units": count} for path, count in totals.most_common(_AREAS)]


def _units_by_file(db: Session, project_id: int, paths: set[str]) -> dict[str, CodeEntity]:
    """Die erste Einheit (Programm, Klasse, Job) je Datei."""
    if not paths:
        return {}
    rows = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.project_id == project_id,
            CodeEntity.file_path.in_(paths),
            CodeEntity.type.in_(CONTAINER_TYPES),
        )
        .order_by(CodeEntity.file_path, CodeEntity.start_line.asc().nullslast())
        .all()
    )
    units: dict[str, CodeEntity] = {}
    for entity in rows:
        units.setdefault(entity.file_path, entity)
    return units


def _unit(entity: CodeEntity | None, path: str) -> dict:
    if entity is None:
        return {"file": path, "cite": f"{path}:1", "lines": [1, 1]}
    start = entity.start_line or 1
    profile = profile_of(entity.type)
    return {
        "unit": entity.name,
        "type": entity.type,
        "language": profile.name if profile else None,
        "file": path,
        "cite": f"{path}:{start}",
        "lines": [start, entity.end_line or start],
    }


def _started_by_other_files(db: Session, project_id: int, paths: list[str]) -> set[str]:
    """Dateien aus ``paths``, in die laut Einzelkanten doch Kontrollfluss aus einer anderen Datei führt."""
    source, target = aliased(CodeEntity), aliased(CodeEntity)
    rows = (
        db.query(target.file_path)
        .select_from(CodeEdge)
        .join(target, target.id == CodeEdge.dst_entity_id)
        .join(source, source.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.project_id == project_id,
            CodeEdge.type.in_(CONTROL_EDGES),
            target.file_path.in_(paths),
            source.file_path != target.file_path,
        )
        .distinct()
        .all()
    )
    return {path for (path,) in rows}


def _control_structure(db: Session, project_id: int) -> tuple[list[dict], list[dict], bool]:
    """Einstiege (starten andere, werden von keiner Datei gestartet), meistgenutzte Einheiten, Vollständigkeit.

    ``code_file_edges`` enthält bei großen Projekten nur das Grundgerüst der Dateikanten. Dann ist „keine
    eingehende Kante“ dort kein Beleg; die Kandidaten werden gegen die Einzelkanten geprüft, und die Zahl der
    nutzenden Dateien ist eine Untergrenze.
    """
    edge = CodeFileEdge
    stored, total = (
        db.query(func.count(), func.max(edge.total_pairs))
        .filter(edge.project_id == project_id)
        .one()
    )
    complete = not stored or stored >= (total or 0)
    scope = (
        edge.project_id == project_id,
        edge.src_file_path != edge.dst_file_path,
        _control_file_edge(edge),
        # Testklassen ruft niemand auf; sie würden sonst jede Liste der Einstiege füllen.
        ~edge.src_file_path.op("~")(TEST_PATH_PATTERN),
        ~edge.dst_file_path.op("~")(TEST_PATH_PATTERN),
    )
    incoming = aliased(CodeFileEdge)
    weight = func.sum(edge.edge_count)
    entry_rows = (
        db.query(edge.src_file_path, func.count(func.distinct(edge.dst_file_path)))
        .filter(
            *scope,
            ~db.query(incoming.id)
            .filter(
                incoming.project_id == project_id,
                incoming.dst_file_path == edge.src_file_path,
                incoming.src_file_path != incoming.dst_file_path,
                _control_file_edge(incoming),
            )
            .exists(),
        )
        .group_by(edge.src_file_path)
        .order_by(func.count(func.distinct(edge.dst_file_path)).desc(), edge.src_file_path)
        .limit(_ENTRY_POINTS if complete else _ENTRY_CANDIDATES)
        .all()
    )
    if not complete and entry_rows:
        started = _started_by_other_files(db, project_id, [path for path, _ in entry_rows])
        entry_rows = [row for row in entry_rows if row[0] not in started][:_ENTRY_POINTS]
    central_rows = (
        db.query(edge.dst_file_path, func.count(func.distinct(edge.src_file_path)))
        .filter(*scope)
        .group_by(edge.dst_file_path)
        .order_by(func.count(func.distinct(edge.src_file_path)).desc(), weight.desc())
        .limit(_CENTRAL_UNITS)
        .all()
    )
    entry_paths = [path for path, _ in entry_rows]
    targets: dict[str, list[str]] = {}
    if entry_paths:
        for src, dst in (
            db.query(edge.src_file_path, edge.dst_file_path)
            .filter(*scope, edge.src_file_path.in_(entry_paths))
            .order_by(edge.src_file_path, edge.edge_count.desc(), edge.dst_file_path)
            .limit(_ENTRY_POINTS * 12)
            .all()
        ):
            if len(targets.setdefault(src, [])) < _NAMED_TARGETS:
                targets[src].append(dst)
    paths = (
        set(entry_paths) | {p for p, _ in central_rows} | {d for v in targets.values() for d in v}
    )
    units = _units_by_file(db, project_id, paths)

    def name(path: str) -> str:
        return units[path].name if path in units else path.rsplit("/", 1)[-1]

    entry_points = [
        {
            **_unit(units.get(path), path),
            "starts": [name(d) for d in targets.get(path, [])],
            "starts_total": total,
        }
        for path, total in entry_rows
    ]
    central = [
        {**_unit(units.get(path), path), "used_by_files": total} for path, total in central_rows
    ]
    return entry_points, central, complete


def _fit(overview: dict, max_chars: int) -> None:
    """Kürzt zuerst die Dokumentauszüge, dann die längsten Listen, bis der Überblick ins Budget passt."""

    def size() -> int:
        return len(json.dumps(overview, ensure_ascii=False))

    for document in overview["documentation"]:
        if size() > max_chars:
            document["excerpt"] = document["excerpt"][:500]
    while size() > max_chars:
        longest = max(("entry_points", "most_used", "areas"), key=lambda key: len(overview[key]))
        if len(overview[longest]) <= 3:
            break
        overview[longest].pop()
        overview["truncated"] = True


def project_overview(db: Session, project_id: int, max_chars: int = 6000) -> dict | None:
    """Überblick über ein Projekt aus dem Index; None, wenn das Projekt keine indizierten Einheiten hat.

    Die Zugriffsprüfung auf das Projekt liegt beim Aufrufer (``build_answer_context``).
    """
    inventory = _inventory(db, project_id)
    documentation = _documentation(db, project_id)
    if not inventory and not documentation:
        return None
    entry_points, central, complete = _control_structure(db, project_id)
    gaps = []
    if not documentation:
        gaps.append("no README at the repository root is indexed")
    if not entry_points and not central:
        gaps.append("no control-flow relations between files are indexed")
    if not complete:
        gaps.append(
            "large project: only the backbone of file relations is precomputed, so `used_by_files` and "
            "`starts_total` are lower bounds"
        )
    overview = {
        "documentation": documentation,
        "inventory": inventory,
        "areas": _areas(db, project_id),
        "entry_points": entry_points,
        "most_used": central,
        "gaps": gaps,
        "notice": (
            "Overview assembled from the index. `entry_points` start other units and are started by none in the "
            "index (jobs, transactions, main classes); this is not proof of how the system is started at runtime. "
            "`most_used` are the units most other files transfer control to. Test code is left out and lists are "
            "capped. Cite the `cite` "
            "fields, and call answer_context with unit names from here for what a unit does."
        ),
    }
    _fit(overview, max_chars)
    return overview
