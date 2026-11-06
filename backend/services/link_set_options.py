"""Bausteine der Analyse-Arbeitsfläche: wählbare Facetten je Mengenart, Suche nach einzelnen Objekten und Vorschau
einer Menge. Die Bedingungen selbst stehen in ``doctus_models.link_sets``; hier nur, was die Oberfläche anzeigt.

Neue Facette: Wertequelle in ``_FACET_VALUES`` ergänzen (und die Bedingung in ``link_sets.FACETS``).
Neue Objektart: Suche in ``_SEARCH`` und Vorschau in ``_SAMPLE`` ergänzen.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy import func, tuple_
from sqlalchemy.orm import Session

from doctus_models.database import CodeEntity, DocumentChunk, KnowledgeSource
from doctus_models.language_profile import profile_of
from doctus_models.link_sets import (
    CODE,
    DOC_ENTITY_TYPES,
    DOCS,
    LinkSet,
    code_scope,
    docs_scope,
)
from services.search import _bound_short_query, _contains, _search_tokens, _tail, search_nodes

# Die Sprachprofile kennen nur Rollen (Container, Routine, Daten). Für die Auswahl gehören auch die übrigen Typen
# einer Sprache in ihre Gruppe; was keine Gruppe hat, steht unter "other".
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
SAMPLE_SIZE = 20
SEARCH_LIMIT = 25


def language_of_type(entity_type: str | None) -> str:
    profile = profile_of(entity_type)
    if profile is not None:
        return profile.name
    if not entity_type:
        return "other"
    if entity_type in _TYPE_LANGUAGES:
        return _TYPE_LANGUAGES[entity_type]
    for prefix, language in _PREFIX_LANGUAGES:
        if entity_type.startswith(prefix):
            return language
    return "other"


def _grouped(
    rows, group_of: Callable, value_of: Callable, label_of: Callable | None = None
) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        entry = {"value": str(value_of(row)), "count": row[-1]}
        if label_of is not None:
            entry["label"] = label_of(row)
        groups.setdefault(group_of(row), []).append(entry)
    result = [
        {
            "key": key,
            "count": sum(item["count"] for item in values),
            "values": sorted(
                values, key=lambda item: (-item["count"], item.get("label") or item["value"])
            ),
        }
        for key, values in groups.items()
    ]
    result.sort(key=lambda group: (group["key"] == "other", -group["count"], group["key"]))
    return result


def _code_entity_types(db: Session, project_id: int) -> list[dict]:
    rows = (
        db.query(CodeEntity.type, func.count(CodeEntity.id))
        .filter(*code_scope(project_id, LinkSet(CODE)), CodeEntity.type.isnot(None))
        .group_by(CodeEntity.type)
    )
    return _grouped(rows, lambda row: language_of_type(row[0]), lambda row: row[0])


def _code_sources(db: Session, project_id: int) -> list[dict]:
    rows = (
        db.query(
            KnowledgeSource.id,
            KnowledgeSource.name,
            KnowledgeSource.type,
            func.count(CodeEntity.id),
        )
        .join(CodeEntity, CodeEntity.source_id == KnowledgeSource.id)
        .filter(*code_scope(project_id, LinkSet(CODE)))
        .group_by(KnowledgeSource.id, KnowledgeSource.name, KnowledgeSource.type)
    )
    return _grouped(rows, lambda row: row[2] or "other", lambda row: row[0], lambda row: row[1])


def _doc_sources(db: Session, project_id: int) -> list[dict]:
    rows = (
        db.query(
            KnowledgeSource.id,
            KnowledgeSource.name,
            KnowledgeSource.type,
            func.count(DocumentChunk.id),
        )
        .join(DocumentChunk, DocumentChunk.source_id == KnowledgeSource.id)
        .filter(*docs_scope(project_id, LinkSet(DOCS)))
        .group_by(KnowledgeSource.id, KnowledgeSource.name, KnowledgeSource.type)
    )
    return _grouped(rows, lambda row: row[2] or "other", lambda row: row[0], lambda row: row[1])


# Mengenart -> (Facette, Wertequelle); die Reihenfolge ist die Anzeige-Reihenfolge.
_FACET_VALUES: dict[str, tuple[tuple[str, Callable[[Session, int], list[dict]]], ...]] = {
    CODE: (("entity_type", _code_entity_types), ("source", _code_sources)),
    DOCS: (("source", _doc_sources),),
}


def kind_options(db: Session, project_id: int, kind: str) -> dict:
    facets = [
        {"name": name, "groups": values(db, project_id)} for name, values in _FACET_VALUES[kind]
    ]
    return {"total": count_set(db, project_id, LinkSet(kind))["count"], "facets": facets}


def count_set(db: Session, project_id: int, link_set: LinkSet) -> dict:
    if link_set.kind == CODE:
        count = (
            db.query(func.count(CodeEntity.id)).filter(*code_scope(project_id, link_set)).scalar()
        )
        return {"count": count or 0}
    conditions = docs_scope(project_id, link_set)
    chunks = db.query(func.count(DocumentChunk.id)).filter(*conditions).scalar() or 0
    documents = (
        db.query(
            func.count(func.distinct(tuple_(DocumentChunk.source_id, DocumentChunk.file_path)))
        )
        .filter(*conditions)
        .scalar()
        or 0
    )
    return {"count": chunks, "documents": documents}


def _entity_item(entity: CodeEntity) -> dict:
    location = f"{entity.file_path}:{entity.start_line}" if entity.start_line else entity.file_path
    return {
        "kind": "entity",
        "id": entity.id,
        "label": entity.name,
        "detail": location or "",
        "entity_type": entity.type,
        "group": language_of_type(entity.type),
    }


def _sample_code(db: Session, project_id: int, link_set: LinkSet) -> list[dict]:
    rows = (
        db.query(CodeEntity)
        .filter(*code_scope(project_id, link_set))
        .order_by(CodeEntity.file_path, CodeEntity.start_line, CodeEntity.id)
        .limit(SAMPLE_SIZE)
    )
    return [_entity_item(entity) for entity in rows]


def _document_rows(db: Session, query, limit: int, rank=None) -> list[dict]:
    """Ein Eintrag je Dokument (Quelle + Datei/Seite/Ticket), mit Titel und Zahl der Abschnitte."""
    title = DocumentChunk.metadata_json["title"].as_string()
    columns = [
        DocumentChunk.source_id,
        DocumentChunk.file_path,
        func.min(title).label("title"),
        func.count(DocumentChunk.id).label("chunks"),
    ]
    order = [DocumentChunk.source_id, DocumentChunk.file_path]
    if rank is not None:
        columns.append(func.min(rank).label("rank"))
        order = ["rank", DocumentChunk.file_path]
    grouped = (
        query.with_entities(*columns)
        .group_by(DocumentChunk.source_id, DocumentChunk.file_path)
        .order_by(*order)
        .limit(limit)
        .all()
    )
    sources = {
        source.id: source
        for source in db.query(KnowledgeSource).filter(
            KnowledgeSource.id.in_({row.source_id for row in grouped})
        )
    }
    items = []
    for row in grouped:
        source = sources.get(row.source_id)
        items.append(
            {
                "kind": "document",
                "source_id": row.source_id,
                "file_path": row.file_path,
                "label": row.title or row.file_path,
                "detail": source.name if source else "",
                "group": (source.type if source else None) or "other",
                "chunk_count": row.chunks,
            }
        )
    return items


def _sample_docs(db: Session, project_id: int, link_set: LinkSet) -> list[dict]:
    query = db.query(DocumentChunk).filter(*docs_scope(project_id, link_set))
    return _document_rows(db, query, SAMPLE_SIZE)


_SAMPLE = {CODE: _sample_code, DOCS: _sample_docs}


def preview(db: Session, project_id: int, link_set: LinkSet) -> dict:
    return {
        **count_set(db, project_id, link_set),
        "sample": _SAMPLE[link_set.kind](db, project_id, link_set),
    }


def _search_code(db: Session, project_id: int, q: str, limit: int) -> list[dict]:
    nodes, _counts = search_nodes(
        db, q=q, types="entity", project_id=project_id, limit=limit + 10, count_total=False
    )
    ids = [
        node["node_id"] for node in nodes if node["node_meta"].get("type") not in DOC_ENTITY_TYPES
    ]
    by_id = {entity.id: entity for entity in db.query(CodeEntity).filter(CodeEntity.id.in_(ids))}
    return [_entity_item(by_id[entity_id]) for entity_id in ids[:limit] if entity_id in by_id]


def _search_docs(db: Session, project_id: int, q: str, limit: int) -> list[dict]:
    tokens = _search_tokens(q)
    if not tokens:
        return []
    title = DocumentChunk.metadata_json["title"].as_string()
    file_name = _tail(DocumentChunk.file_path)
    query = db.query(DocumentChunk).filter(*docs_scope(project_id, LinkSet(DOCS)))
    for token in tokens:
        query = query.filter(_contains(title, token) | _contains(file_name, token))
    query = _bound_short_query(db, query, DocumentChunk, tokens)
    phrase = q.strip().lower()
    rank = func.coalesce(func.nullif(func.strpos(func.lower(title), phrase), 0), 1000)
    return _document_rows(db, query, limit, rank=rank)


_SEARCH = {CODE: _search_code, DOCS: _search_docs}


def search(
    db: Session, project_id: int, kind: str, q: str, limit: int = SEARCH_LIMIT
) -> list[dict]:
    if not q.strip():
        return []
    return _SEARCH[kind](db, project_id, q, max(1, min(limit, 100)))
