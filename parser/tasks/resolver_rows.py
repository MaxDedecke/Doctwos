"""Schlanke Zeilen für die Auflöser am Sync-Ende.

Ein Bestand wie Apache Camel hat 2,3 Mio. Code-Elemente und 3 Mio. Beziehungen. Als ORM-Objekte
sprengen sie jedes Speicherlimit. Teuer sind vor allem die Metadaten: große Felder, die ein Auflöser
gar nicht liest, und dieselben Texte millionenfach als eigene Objekte. Diese Zeilen lassen solche
Felder weg und teilen gleiche Texte. Sie sind nur zum Lesen da: Schreiben geht über das ORM oder
`bulk_update_edges`/`bulk_update_entity_meta`.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Iterable
from sys import intern
from typing import Any

from doctus_models.database import CodeEdge, CodeEntity
from sqlalchemy import text
from sqlalchemy.orm import Session

_BATCH = 2000
_MAX_SHARED_LENGTH = 300


def share(value: Any) -> Any:
    """Gleiche Texte (Klassennamen, Schlüssel, Arten) belegen so nur einmal Speicher."""
    if isinstance(value, str):
        return intern(value) if len(value) <= _MAX_SHARED_LENGTH else value
    if isinstance(value, list):
        return [share(item) for item in value]
    if isinstance(value, dict):
        return {intern(key): share(item) for key, item in value.items()}
    return value


def slim_meta(meta: dict | None, drop: frozenset[str] = frozenset()) -> dict:
    return {intern(key): share(item) for key, item in (meta or {}).items() if key not in drop}


def meta_checksum(meta: dict | None) -> int:
    """Zum Erkennen geänderter Metadaten, ohne jede Zeile doppelt im Speicher zu halten."""
    return zlib.crc32(json.dumps(meta or {}, sort_keys=True, default=str).encode())


class EntityRow:
    __slots__ = (
        "checksum",
        "end_line",
        "file_path",
        "id",
        "meta_json",
        "name",
        "parent_id",
        "project_id",
        "qualified_name",
        "start_line",
        "type",
        "variant_key",
    )

    def __init__(self, row, meta: dict):
        self.id = row.id
        self.project_id = row.project_id
        self.type = intern(row.type) if row.type else row.type
        self.name = share(row.name)
        self.qualified_name = share(row.qualified_name)
        self.variant_key = intern(row.variant_key)
        self.file_path = share(row.file_path)
        self.start_line = row.start_line
        self.end_line = row.end_line
        self.parent_id = row.parent_id
        self.meta_json = meta
        self.checksum = 0


class EdgeRow:
    __slots__ = (
        "checksum",
        "dst_entity_id",
        "dst_name",
        "id",
        "meta_json",
        "resolution",
        "scope_entity_id",
        "src_end_line",
        "src_entity_id",
        "src_start_line",
        "type",
        "variant_key",
    )

    def __init__(self, row, meta: dict):
        self.id = row.id
        self.type = intern(row.type)
        self.src_entity_id = row.src_entity_id
        self.dst_entity_id = row.dst_entity_id
        self.dst_name = share(row.dst_name)
        self.resolution = intern(row.resolution)
        self.scope_entity_id = row.scope_entity_id
        self.src_start_line = row.src_start_line
        self.src_end_line = row.src_end_line
        self.variant_key = intern(row.variant_key)
        self.meta_json = meta
        self.checksum = 0


def load_entity_rows(
    db: Session,
    *criteria,
    drop: frozenset[str] = frozenset(),
    keep_full: frozenset[str] = frozenset(),
) -> list[EntityRow]:
    """`keep_full`: Elementarten, deren Metadaten vollständig bleiben."""
    query = db.query(
        CodeEntity.id,
        CodeEntity.project_id,
        CodeEntity.type,
        CodeEntity.name,
        CodeEntity.qualified_name,
        CodeEntity.variant_key,
        CodeEntity.file_path,
        CodeEntity.start_line,
        CodeEntity.end_line,
        CodeEntity.parent_id,
        CodeEntity.meta_json,
    ).filter(*criteria)
    return [
        EntityRow(
            row, (row.meta_json or {}) if row.type in keep_full else slim_meta(row.meta_json, drop)
        )
        for row in query.yield_per(5000)
    ]


def load_edge_rows(db: Session, *criteria, drop: frozenset[str] = frozenset()) -> list[EdgeRow]:
    query = db.query(
        CodeEdge.id,
        CodeEdge.type,
        CodeEdge.src_entity_id,
        CodeEdge.dst_entity_id,
        CodeEdge.dst_name,
        CodeEdge.resolution,
        CodeEdge.scope_entity_id,
        CodeEdge.src_start_line,
        CodeEdge.src_end_line,
        CodeEdge.variant_key,
        CodeEdge.meta_json,
    ).filter(*criteria)
    return [EdgeRow(row, slim_meta(row.meta_json, drop)) for row in query.yield_per(5000)]


def _merged_meta(alias: str, dropped: Iterable[str]) -> str:
    """Neue Metadaten plus die beim Laden weggelassenen Felder aus der Zeile; leer wird NULL."""
    names = ",".join("'" + name + "'" for name in sorted(dropped))
    kept = (
        f"(SELECT jsonb_object_agg(o.key, o.value) FROM jsonb_each({alias}.meta_json::jsonb) AS o "
        f"WHERE o.key IN ({names}))"
        if names
        else "NULL"
    )
    return (
        f"CAST(NULLIF(COALESCE(CAST(v.meta AS jsonb), '{{}}'::jsonb) || "
        f"COALESCE({kept}, '{{}}'::jsonb), '{{}}'::jsonb) AS json)"
    )


def bulk_update_edges(db: Session, updates: list[tuple], dropped: frozenset[str]) -> int:
    """`updates`: (id, dst_entity_id, resolution, meta). Bricht die Transaktion nicht auf."""
    statement = text(
        "UPDATE code_edges AS e SET dst_entity_id = v.dst, resolution = v.res, "
        f"meta_json = {_merged_meta('e', dropped)} "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:dsts AS integer[]), CAST(:res AS text[]), "
        "CAST(:metas AS text[])) AS v(id, dst, res, meta) WHERE e.id = v.id"
    )
    for start in range(0, len(updates), _BATCH):
        batch = updates[start : start + _BATCH]
        db.execute(
            statement,
            {
                "ids": [item[0] for item in batch],
                "dsts": [item[1] for item in batch],
                "res": [item[2] for item in batch],
                "metas": [json.dumps(item[3]) if item[3] else None for item in batch],
            },
        )
    return len(updates)


def bulk_update_entity_meta(db: Session, updates: list[tuple], dropped: frozenset[str]) -> int:
    """`updates`: (id, meta)."""
    statement = text(
        f"UPDATE code_entities AS e SET meta_json = {_merged_meta('e', dropped)} "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:metas AS text[])) AS v(id, meta) "
        "WHERE e.id = v.id"
    )
    for start in range(0, len(updates), _BATCH):
        batch = updates[start : start + _BATCH]
        db.execute(
            statement,
            {
                "ids": [item[0] for item in batch],
                "metas": [json.dumps(item[1]) if item[1] else None for item in batch],
            },
        )
    return len(updates)
