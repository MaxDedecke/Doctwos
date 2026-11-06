"""Einschränkung eines Entity-Link-Laufs auf zwei Mengen: Code-Entitäten gewählter Typen und Dokumentation
gewählter Wissensquellen. Der Parser liest dasselbe Format (``parser/tasks/link_run_scope.py``)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from doctus_models.database import CodeEntity, DocumentChunk, KnowledgeSource, LinkBuilderRun
from doctus_models.language_profile import profile_of

# Dokumentations-Entitäten werden nie als Code-Seite geprüft (parser/core/doc_resolution.py::DOC_ENTITY_TYPES).
DOC_ENTITY_TYPES = frozenset({"asciidoc_document", "doc_section"})
DOC_LANGUAGES = ("asciidoc", "markdown", "text")

# Die Sprachprofile kennen nur Rollen (Container, Routine, Daten). Für die Auswahl im Link-Manager gehören auch
# die übrigen Typen einer Sprache in ihre Gruppe; was keine Gruppe hat, steht unter "other".
_TYPE_LANGUAGES = {
    "copybook": "cobol",
    "entry": "cobol",
    "exec_block": "cobol",
    "exec_operation": "cobol",
    "exec_resource": "cobol",
    "cics_file": "cobol",
    "csd_file": "cobol",
    "sql_block": "cobol",
    "sql_include": "cobol",
    "compilation_unit": "java",
    "package": "java",
    "method_reference": "java",
    "xml_document": "xml",
    "spring_bean": "xml",
}
_PREFIX_LANGUAGES = (
    ("jcl_", "jcl"),
    ("maven_", "maven"),
    ("xsd_", "xml"),
    ("wsdl_", "xml"),
    ("xslt_", "xml"),
    ("sql_", "sql"),
    ("shell_", "shell"),
)
MAX_FILTER_TYPES = 200
MAX_FILTER_SOURCES = 200


def language_of_type(entity_type: str) -> str:
    profile = profile_of(entity_type)
    if profile is not None:
        return profile.name
    if entity_type in _TYPE_LANGUAGES:
        return _TYPE_LANGUAGES[entity_type]
    for prefix, language in _PREFIX_LANGUAGES:
        if entity_type.startswith(prefix):
            return language
    return "other"


def documentation_condition():
    """Wie der Parser: Inhalte nicht-Git-Quellen und Doku-Dateien in Git-Quellen sind Dokumentation."""
    return or_(
        KnowledgeSource.type != "Git",
        DocumentChunk.metadata_json["language"].as_string().in_(DOC_LANGUAGES),
    )


def normalize_filter(
    db: Session,
    project_id: int,
    entity_types: list[str] | None,
    doc_source_ids: list[int] | None,
) -> dict | None:
    """Prüft die Auswahl und liefert ``scope_json["filter"]``; ``None`` heißt: keine Einschränkung."""
    types = sorted({value.strip() for value in entity_types or [] if value and value.strip()})
    sources = sorted({int(value) for value in doc_source_ids or []})
    if len(types) > MAX_FILTER_TYPES or len(sources) > MAX_FILTER_SOURCES:
        raise HTTPException(status_code=422, detail="Zu viele Einträge in der Auswahl")
    if DOC_ENTITY_TYPES.intersection(types):
        raise HTTPException(
            status_code=422, detail="Dokumentations-Typen sind keine Code-Seite eines Laufs"
        )
    if sources:
        owned = {
            row[0]
            for row in db.query(KnowledgeSource.id).filter(
                KnowledgeSource.id.in_(sources), KnowledgeSource.project_id == project_id
            )
        }
        if owned != set(sources):
            raise HTTPException(
                status_code=422, detail="Alle Wissensquellen müssen zum Projekt gehören"
            )
    if not types and not sources:
        return None
    return {"entity_types": types, "doc_source_ids": sources}


def is_targeted(scope: dict | None) -> bool:
    raw = (scope or {}).get("filter")
    return isinstance(raw, dict) and bool(raw.get("entity_types") or raw.get("doc_source_ids"))


def had_full_run(db: Session, project_id: int) -> bool:
    """Ein abgeschlossener Lauf ohne Einschränkung; ein eingeschränkter Lauf ersetzt den Erstlauf nicht."""
    rows = db.query(LinkBuilderRun.scope_json).filter(
        LinkBuilderRun.project_id == project_id,
        LinkBuilderRun.task_type == "entity_links",
        LinkBuilderRun.status == "completed",
    )
    return any(not is_targeted(scope) for (scope,) in rows)


def targeted_estimate(db: Session, project_id: int, run_filter: dict) -> dict:
    entities, chunks = _filtered_counts(db, project_id, run_filter)
    to_scan = entities if chunks else 0
    return {
        "entity_count": entities,
        "chunk_count": chunks,
        "dirty_entity_count": 0,
        "dirty_chunk_count": 0,
        "is_bootstrap": False,
        "is_targeted": True,
        "entities_to_scan": to_scan,
        "cost_notice": (
            f"Eingeschränkter Lauf: {entities} Code-Entitäten gegen {chunks} Dokument-Abschnitte."
        ),
        "estimated_llm_reviews_max": to_scan,
        "estimated_embedding_calls_max": to_scan,
        "estimate_kind": "upper_bound",
    }


def _filtered_counts(db: Session, project_id: int, run_filter: dict) -> tuple[int, int]:
    """Code-Entitäten und Dokumentations-Abschnitte, die ein eingeschränkter Lauf gegeneinander prüft."""
    entity_query = db.query(func.count(CodeEntity.id)).filter(
        CodeEntity.project_id == project_id, CodeEntity.type.notin_(DOC_ENTITY_TYPES)
    )
    if run_filter.get("entity_types"):
        entity_query = entity_query.filter(CodeEntity.type.in_(run_filter["entity_types"]))
    chunk_query = (
        db.query(func.count(DocumentChunk.id))
        .join(KnowledgeSource, KnowledgeSource.id == DocumentChunk.source_id)
        .filter(DocumentChunk.project_id == project_id, documentation_condition())
    )
    if run_filter.get("doc_source_ids"):
        chunk_query = chunk_query.filter(DocumentChunk.source_id.in_(run_filter["doc_source_ids"]))
    return entity_query.scalar() or 0, chunk_query.scalar() or 0


def scope_options(db: Session, project_id: int) -> dict:
    """Wählbare Typen je Sprache und Wissensquellen mit Dokumentation, dazu die Auswahl des letzten Laufs."""
    languages: dict[str, list[dict]] = {}
    type_rows = (
        db.query(CodeEntity.type, func.count(CodeEntity.id))
        .filter(
            CodeEntity.project_id == project_id,
            CodeEntity.type.isnot(None),
            CodeEntity.type.notin_(DOC_ENTITY_TYPES),
        )
        .group_by(CodeEntity.type)
    )
    for entity_type, count in type_rows:
        languages.setdefault(language_of_type(entity_type), []).append(
            {"type": entity_type, "count": count}
        )
    language_list = [
        {
            "language": language,
            "count": sum(item["count"] for item in types),
            "types": sorted(types, key=lambda item: (-item["count"], item["type"])),
        }
        for language, types in languages.items()
    ]
    language_list.sort(key=lambda item: (item["language"] == "other", -item["count"]))

    source_rows = (
        db.query(
            KnowledgeSource.id,
            KnowledgeSource.name,
            KnowledgeSource.type,
            func.count(DocumentChunk.id),
        )
        .join(DocumentChunk, DocumentChunk.source_id == KnowledgeSource.id)
        .filter(KnowledgeSource.project_id == project_id, documentation_condition())
        .group_by(KnowledgeSource.id, KnowledgeSource.name, KnowledgeSource.type)
        .order_by(KnowledgeSource.type, KnowledgeSource.name)
    )
    sources = [
        {"id": source_id, "name": name, "type": source_type, "chunk_count": count}
        for source_id, name, source_type, count in source_rows
    ]

    # Die Auswahl gilt je Projekt (Modul): Der letzte von einer Person gestartete Lauf gibt sie vor.
    last_run = (
        db.query(LinkBuilderRun.scope_json)
        .filter(
            LinkBuilderRun.project_id == project_id,
            LinkBuilderRun.task_type == "entity_links",
            LinkBuilderRun.triggered_by_user_id.isnot(None),
        )
        .order_by(LinkBuilderRun.id.desc())
        .first()
    )
    last_filter = ((last_run[0] or {}).get("filter") if last_run else None) or None
    return {
        "project_id": project_id,
        "languages": language_list,
        "doc_sources": sources,
        "last_filter": last_filter,
    }
