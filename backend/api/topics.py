"""
backend/api/topics.py
======================
Topic-Hub: Verknüpft beliebige Nodes (Repository, Entity, Dokument, Wissensquelle)
unter einem gemeinsamen Thema. Ein Topic ist ein benannter Knoten, dem man per
POST /{id}/nodes beliebige andere Nodes anhängen kann.

Endpoints:
    GET    /topics                   — alle Topics mit Node-Anzahl
    POST   /topics                   — neues Topic anlegen
    PATCH  /topics/{id}              — Name / Beschreibung / Farbe ändern
    DELETE /topics/{id}              — Topic + alle Nodes löschen
    GET    /topics/{id}/nodes        — alle Nodes eines Topics
    POST   /topics/{id}/nodes        — Node anhängen
    DELETE /topics/{id}/nodes/{nid}  — Node lösen
    GET    /topics/search-nodes      — typenübergreifende Node-Suche
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.db_setup import get_db
from models.database import Topic, TopicNode, User
from api.schemas import TopicCreate, TopicUpdate, TopicNodeAttach
from api.serializers import serialize_topic, serialize_topic_node
from services.search import search_nodes as _search_nodes, ALL_TYPES
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids
from core.projects import get_visible_project_ids

router = APIRouter(prefix="/topics", tags=["topics"])


# ── Search (before /{topic_id} routes to avoid param collision) ──────────────

@router.get("/search-nodes")
def search_nodes(
    q: str = "",
    types: str = ALL_TYPES,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Searches for nodes (project, entity, document, knowledge source) that can be added to a topic.
    Uses central search logic from services/search.py.
    """
    team_ids = get_visible_team_ids(user, db)
    project_ids = get_visible_project_ids(user, db)
    results, _counts = _search_nodes(
        db, q=q, types=types,
        visible_team_ids=team_ids,
        visible_project_ids=project_ids
    )
    return results


# ── Topic CRUD ────────────────────────────────────────────────────────────────

@router.get("")
def list_topics(db: Session = Depends(get_db)):
    """
    Lists all existing topics.
    """
    topics = db.query(Topic).order_by(Topic.created_at.desc()).all()
    return [serialize_topic(t) for t in topics]


@router.post("", status_code=201)
def create_topic(data: TopicCreate, db: Session = Depends(get_db)):
    """
    Creates a new topic (theme container).
    """
    t = Topic(name=data.name, description=data.description, color=data.color or "indigo")
    db.add(t)
    db.commit()
    db.refresh(t)
    return serialize_topic(t)


@router.patch("/{topic_id}")
def update_topic(topic_id: int, data: TopicUpdate, db: Session = Depends(get_db)):
    """
    Updates metadata of a topic.
    """
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topic not found")
    if data.name is not None:
        t.name = data.name
    if data.description is not None:
        t.description = data.description
    if data.color is not None:
        t.color = data.color
    db.commit()
    db.refresh(t)
    return serialize_topic(t)


@router.delete("/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db)):
    """
    Deletes a topic and all its node links (TopicNode).
    The actual entities/documents remain untouched.
    """
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topic not found")
    db.delete(t)
    db.commit()
    return {"message": "Topic deleted"}


# ── Node management ───────────────────────────────────────────────────────────

@router.get("/{topic_id}/nodes")
def list_topic_nodes(topic_id: int, db: Session = Depends(get_db)):
    """
    Lists all nodes assigned to a specific topic.
    """
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topic not found")
    return [serialize_topic_node(n) for n in t.nodes]


@router.post("/{topic_id}/nodes", status_code=201)
def attach_node(topic_id: int, data: TopicNodeAttach, db: Session = Depends(get_db)):
    """
    Adds a node (e.g., a code section or a Confluence document) to a topic.
    Used for grouping knowledge across repository boundaries.
    """
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Topic not found")
    existing = (
        db.query(TopicNode)
        .filter(
            TopicNode.topic_id == topic_id,
            TopicNode.node_type == data.node_type,
            TopicNode.node_id == data.node_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Node already linked")
    n = TopicNode(
        topic_id=topic_id,
        node_type=data.node_type,
        node_id=data.node_id,
        node_label=data.node_label,
        node_url=data.node_url,
        node_meta=data.node_meta,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return serialize_topic_node(n)


@router.delete("/{topic_id}/nodes/{node_id}")
def detach_node(topic_id: int, node_id: int, db: Session = Depends(get_db)):
    """
    Removes a node link from a topic.
    """
    n = (
        db.query(TopicNode)
        .filter(TopicNode.id == node_id, TopicNode.topic_id == topic_id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Node link not found")
    db.delete(n)
    db.commit()
    return {"message": "Node removed"}


