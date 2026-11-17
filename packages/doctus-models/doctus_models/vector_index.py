"""HNSW-Indizes der Abschnittsvektoren je Dimension.

``document_chunks.embedding`` hat keine feste Dimension (mehrere Modelle in einer Tabelle). Jede genutzte Dimension
bekommt einen eigenen Teilindex auf ``embedding::vector(n)`` bzw. ``::halfvec(n)`` mit ``WHERE embedding_dimension =
n``; eine Abfrage nutzt ihn nur mit genau derselben Umwandlung. pgvector indiziert ``vector`` bis 2000 und ``halfvec``
bis 4000 Dimensionen; darüber bleibt nur der vollständige Durchlauf.

Die Indizes für 1024 und 2560 legt die Migration 0015 an; weitere entstehen beim Modellwechsel eines Projekts.
"""

from __future__ import annotations

from typing import Optional

from pgvector.sqlalchemy import HALFVEC, Vector

VECTOR_MAX = 2000
HALFVEC_MAX = 4000


def indexed_type(dimension: int):
    """Typ, auf den der Index der Dimension die Spalte umwandelt; None, wenn sie nicht indizierbar ist."""
    if 0 < dimension <= VECTOR_MAX:
        return Vector(dimension)
    if dimension <= HALFVEC_MAX:
        return HALFVEC(dimension)
    return None


def index_name(dimension: int) -> str:
    return f"idx_document_chunks_embedding_{int(dimension)}_hnsw"


def create_index_sql(dimension: int) -> Optional[str]:
    dimension = int(dimension)
    if 0 < dimension <= VECTOR_MAX:
        expression, ops = f"(embedding::vector({dimension}))", "vector_cosine_ops"
    elif dimension <= HALFVEC_MAX:
        expression, ops = f"(embedding::halfvec({dimension}))", "halfvec_cosine_ops"
    else:
        return None
    return (
        f"CREATE INDEX IF NOT EXISTS {index_name(dimension)} ON document_chunks "
        f"USING hnsw ({expression} {ops}) WHERE embedding_dimension = {dimension}"
    )
