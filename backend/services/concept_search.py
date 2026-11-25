"""Auffinden nach Beschreibung statt nach Namen (Baustein des Belegpakets und von ``search_code``).

Fragen wie „Wo prüfe ich das Kreditlimit?“ oder „Wie wird ein Benutzer gelöscht?“ nennen keinen Bezeichner; die
Namenssuche findet dafür nichts (im Benchmark waren 58 von 76 Aufrufen leer). Dieser Baustein liefert dann die
besten Textstellen des Index, je Datei die eine beste, jeweils der Einheit zugeordnet, zu der die Stelle gehört
(Programm, Absatz, Klasse, Methode), mit Fundstelle. Er liest nur Rollen aus dem ``LanguageProfile``.

Zwei Signale, in dieser Reihenfolge: Ähnlichkeit des Anfragevektors zu den Abschnitten des Projekts und
Bezeichner, die mehrere Begriffe der Anfrage enthalten. Ist die Einbettung nicht verfügbar, bleiben die Bezeichner.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.projects import assert_knowledge_source_visible
from codena_models.database import CodeEntity, DocumentChunk, KnowledgeSource, User
from codena_models.language_profile import CONTAINER_TYPES, ROUTINE_TYPES
from services.call_flow import TEST_PATH_PATTERN
from services.ollama_client import embed_text, nearest_project_chunks

logger = logging.getLogger(__name__)

_STOP = frozenset(
    "der die das den dem des ein eine einer und oder nicht mit wie wird werden wurde wo was welche welcher welches "
    "wenn bei von für fuer auf aus nach vor über ueber ist sind hat haben kann soll muss ich wir man dass sich "
    "the and for with that this how what which where when does into from are was has have can should must "
    "ihre ihrem unter dieser diese dieses dabei dafür dazu auch noch nur oder jeder jede jedes zwischen".split()
)
_MIN_TERM = 4
_POOL_PER_HIT = 12
# Tickets, Dokumentation und Tests dürfen den Produktivcode ergänzen, nicht verdrängen.
_MAX_TESTS = 2
_MAX_OTHER = 2
_TEST_RE = re.compile(TEST_PATH_PATTERN)


def chunk_in_project(db: Session, user: User, project_id: int, chunk: DocumentChunk) -> bool:
    """Require both the requested project scope and its optional source ACL."""
    if chunk.project_id not in (None, project_id):
        return False
    if chunk.source_id is None:
        # Source-less Git chunks belong to a project directly. Unscoped legacy
        # chunks must not become visible just because they have no source ACL.
        return chunk.project_id == project_id
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == chunk.source_id).first()
    if source is None or source.project_id != project_id:
        return False
    try:
        assert_knowledge_source_visible(source, user, db)
    except HTTPException:
        return False
    return True


def _terms(query: str) -> list[str]:
    seen = dict.fromkeys(
        t.lower() for t in re.findall(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß]+", query) if len(t) >= _MIN_TERM
    )
    return [t for t in seen if t not in _STOP][:8]


def _embed_query(db: Session, project_id: int, query: str) -> list[float] | None:
    from services.answer_context import _embedding_profile_for_project

    try:
        profile = _embedding_profile_for_project(db, project_id)
        config = {
            "model": profile.model,
            "provider": profile.provider,
            "base_url": profile.base_url,
            "path": profile.path,
            "api_key": profile.api_key,
            "dimension": profile.dimension,
            "context_length": profile.context_length,
        }
        # FastMCP ruft synchrone Werkzeuge auf der Ereignisschleife des Servers auf; die Einbettung bekommt eine eigene.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run, embed_text(query[:480], is_query=True, **config)
            ).result(timeout=20)
    except (
        Exception
    ) as exc:  # Einbettungsdienst fehlt oder falsches Profil: Bezeichnersignal bleibt
        logger.info("concept search without embedding (%s: %s)", type(exc).__name__, str(exc)[:160])
        return None


def _code_files(db: Session, project_id: int, paths: set[str]) -> set[str]:
    """Dateien mit Routinen oder Containern laut Sprachprofil (Code, im Gegensatz zu Tickets, Dokumentation, Konfiguration)."""
    if not paths:
        return set()
    rows = (
        db.query(CodeEntity.file_path)
        .filter(
            CodeEntity.project_id == project_id,
            CodeEntity.file_path.in_(paths),
            CodeEntity.type.in_(ROUTINE_TYPES | CONTAINER_TYPES),
        )
        .distinct()
        .all()
    )
    return {path for (path,) in rows}


def _unit_of(db: Session, project_id: int, chunk: DocumentChunk) -> CodeEntity | None:
    """Kleinste Routine, sonst Container, die den Beginn des Abschnitts enthält."""
    if not chunk.file_path:
        return None
    line = chunk.start_line or 1
    rows = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.project_id == project_id,
            CodeEntity.file_path == chunk.file_path,
            CodeEntity.type.in_(ROUTINE_TYPES | CONTAINER_TYPES),
            CodeEntity.start_line <= line,
            or_(CodeEntity.end_line.is_(None), CodeEntity.end_line >= line),
        )
        .all()
    )
    if not rows:
        return None
    return min(rows, key=lambda e: ((e.end_line or 10**9) - (e.start_line or 0), e.id))


def _name_hits(db: Session, project_id: int, terms: list[str], limit: int) -> list[CodeEntity]:
    """Einheiten, deren Name mehrere Begriffe der Anfrage enthält (bei kurzer Anfrage: einen)."""
    terms = terms[:4]
    if not terms:
        return []
    squashed = func.lower(func.replace(func.replace(CodeEntity.name, "-", ""), "_", ""))
    candidates: dict[int, CodeEntity] = {}
    for term in terms:
        for entity in (
            db.query(CodeEntity)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.type.in_(ROUTINE_TYPES | CONTAINER_TYPES),
                squashed.like(f"%{term}%"),
            )
            .limit(60)
            .all()
        ):
            candidates[entity.id] = entity
    need = 2 if len(terms) > 2 else 1

    def score(entity: CodeEntity) -> int:
        name = re.sub(r"[-_]", "", (entity.name or "").lower())
        return sum(term in name for term in terms)

    ranked = sorted(
        (e for e in candidates.values() if score(e) >= need),
        key=lambda e: (-score(e), len(e.name or ""), e.id),
    )
    return ranked[:limit]


def concept_hits(
    db: Session, user: User, project_id: int, query: str, limit: int = 8
) -> dict | None:
    """Beste Fundstellen zu einer Beschreibung; None, wenn nichts zu finden war.

    Die Zugriffsprüfung auf das Projekt liegt beim Aufrufer; Abschnitte werden zusätzlich je Quelle geprüft.
    """
    query = (query or "").strip()
    if not query:
        return None
    hits: list[dict] = []
    seen_files: set[str] = set()
    vector = _embed_query(db, project_id, query)
    pool = (
        nearest_project_chunks(db, project_id, vector, limit=limit * _POOL_PER_HIT)
        if vector
        else []
    )
    code = _code_files(db, project_id, {c.file_path for c in pool if c.file_path})

    def kind(chunk: DocumentChunk) -> int:
        if chunk.file_path not in code:
            return 2
        return 1 if _TEST_RE.search(chunk.file_path or "") else 0

    chunks: list[DocumentChunk] = []
    taken = {1: 0, 2: 0}
    for chunk in sorted(
        pool, key=kind
    ):  # stabil: innerhalb einer Art bleibt die Reihenfolge der Ähnlichkeit
        k = kind(chunk)
        if k and taken[k] >= (_MAX_TESTS if k == 1 else _MAX_OTHER):
            continue
        if k:
            taken[k] += 1
        chunks.append(chunk)
    for chunk in chunks:
        if chunk.file_path in seen_files or not chunk_in_project(db, user, project_id, chunk):
            continue
        seen_files.add(chunk.file_path)
        unit = _unit_of(db, project_id, chunk)
        start = chunk.start_line or 1
        hits.append(
            {
                "cite": f"{chunk.file_path}:{start}",
                "file": chunk.file_path,
                "lines": [start, chunk.end_line or start],
                "unit": (unit.qualified_name or unit.name) if unit else None,
                "unit_type": unit.type if unit else None,
                "via": "semantic",
                "excerpt": (chunk.content or "").strip()[:360],
            }
        )
        if len(hits) >= limit:
            break
    named = 0
    # Das Bezeichnersignal ist das zweite: Die Namenssuche liest alle Einheiten des Projekts und kostet bei sehr
    # großen Beständen Sekunden. Sie läuft nur, wenn die Textsuche zu wenig oder nichts geliefert hat.
    needs_names = vector is None or len(hits) < max(2, limit // 2)
    for entity in _name_hits(db, project_id, _terms(query), limit) if needs_names else []:
        if entity.file_path in seen_files or len(hits) >= limit + 3:
            continue
        seen_files.add(entity.file_path)
        start = entity.start_line or 1
        named += 1
        hits.append(
            {
                "cite": f"{entity.file_path}:{start}",
                "file": entity.file_path,
                "lines": [start, entity.end_line or start],
                "unit": entity.qualified_name or entity.name,
                "unit_type": entity.type,
                "via": "name",
            }
        )
    if not hits:
        return None
    return {
        "mode": "semantic+names" if vector and named else "semantic" if vector else "names",
        "hits": hits,
        "notice": (
            "No symbol was named, so these are the best passages for the description, one per file, with the unit "
            "each belongs to. They are retrieval hints, not verified conclusions: name the unit in answer_context "
            "(symbols=[...]) or explain_symbol for its source, callers and data access, and cite the `cite` fields."
        ),
    }
