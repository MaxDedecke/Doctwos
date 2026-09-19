"""Tests for edge directionality modeling (O-264).

Validates:
- KnowledgeLink.direction column with defaults and explicit values ('undirected', 'directed', 'bidirectional')
- CodeEdge.direction standard property ('directed')
- EntityDocLink.direction standard property ('directed')
- Shared constants and synchronization across backend and parser models
"""

import pytest
from sqlalchemy.orm import Session

from models.database import (
    EDGE_DIRECTION_BIDIRECTIONAL,
    EDGE_DIRECTION_DIRECTED,
    EDGE_DIRECTION_UNDIRECTED,
    VALID_EDGE_DIRECTIONS,
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeLink,
    KnowledgeSource,
    Project,
)


def test_edge_direction_constants():
    assert EDGE_DIRECTION_DIRECTED == "directed"
    assert EDGE_DIRECTION_UNDIRECTED == "undirected"
    assert EDGE_DIRECTION_BIDIRECTIONAL == "bidirectional"
    assert VALID_EDGE_DIRECTIONS == {"directed", "undirected", "bidirectional"}


def test_code_edge_standard_direction():
    edge = CodeEdge(
        src_entity_id=1,
        dst_name="TARGET-PARA",
        type="CALL",
        resolution="unresolved",
    )
    assert edge.direction == EDGE_DIRECTION_DIRECTED


def test_entity_doc_link_standard_direction():
    link = EntityDocLink(
        entity_id=1,
        doc_title="API Reference",
        link_type="semantic",
        status="approved",
    )
    assert link.direction == EDGE_DIRECTION_DIRECTED


def test_knowledge_link_default_direction(db_session: Session):
    link = KnowledgeLink(
        source_a_type="document",
        source_a_title="Architecture.md",
        source_b_type="document",
        source_b_title="Overview.md",
        link_type="semantic",
        status="pending",
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    assert link.direction == EDGE_DIRECTION_UNDIRECTED

    # Clean up
    db_session.delete(link)
    db_session.commit()


def test_knowledge_link_explicit_directed(db_session: Session):
    link = KnowledgeLink(
        source_a_type="document",
        source_a_title="ServiceA.md",
        source_b_type="document",
        source_b_title="ServiceB.md",
        link_type="manual",
        status="approved",
        direction=EDGE_DIRECTION_DIRECTED,
    )
    db_session.add(link)
    db_session.commit()
    db_session.refresh(link)

    assert link.direction == EDGE_DIRECTION_DIRECTED

    # Can update to bidirectional
    link.direction = EDGE_DIRECTION_BIDIRECTIONAL
    db_session.commit()
    db_session.refresh(link)
    assert link.direction == EDGE_DIRECTION_BIDIRECTIONAL

    # Clean up
    db_session.delete(link)
    db_session.commit()
