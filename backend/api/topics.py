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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.db_setup import get_db
from doctus_models.database import Topic, TopicNode, User
from api.schemas import TopicCreate, TopicUpdate, TopicNodeAttach
from api.serializers import serialize_topic, serialize_topic_node
from services.search import search_nodes as _search_nodes, ALL_TYPES
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids
from core.projects import get_visible_project_ids
from services.link_project_scope import assert_link_project
from services.topic_project_scope import get_scoped_topic, assert_topic_node_project

router = APIRouter(prefix="/topics", tags=["topics"])


# ── Search (before /{topic_id} routes to avoid param collision) ──────────────


@router.get("/search-nodes")
def search_nodes(
    q: str = "",
    types: str = ALL_TYPES,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Searches for nodes (project, entity, document, knowledge source) that can be added to a topic.
    Uses central search logic from services/search.py.
    """
    if project_id is not None:
        assert_link_project(project_id, user, db)
    team_ids = get_visible_team_ids(user, db)
    project_ids = get_visible_project_ids(user, db)
    results, _counts = _search_nodes(
        db,
        q=q,
        types=types,
        project_id=project_id,
        visible_team_ids=team_ids,
        visible_project_ids=project_ids,
    )
    return results


# ── Topic CRUD ────────────────────────────────────────────────────────────────


@router.get("")
def list_topics(
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Lists all existing topics.
    """
    if project_id is not None:
        assert_link_project(project_id, user, db)
    query = db.query(Topic)
    if project_id is not None:
        query = query.filter(Topic.project_id == project_id)
    topics = query.order_by(Topic.created_at.desc()).all()
    return [serialize_topic(t) for t in topics]


@router.post("", status_code=201)
def create_topic(
    data: TopicCreate,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Creates a new topic (theme container).
    """
    if project_id is not None:
        assert_link_project(project_id, user, db)
    t = Topic(
        project_id=project_id,
        name=data.name,
        description=data.description,
        color=data.color or "indigo",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return serialize_topic(t)


@router.patch("/{topic_id}")
def update_topic(
    topic_id: int,
    data: TopicUpdate,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Updates metadata of a topic.
    """
    t = get_scoped_topic(topic_id, project_id, user, db)
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
def delete_topic(
    topic_id: int,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Deletes a topic and all its node links (TopicNode).
    The actual entities/documents remain untouched.
    """
    t = get_scoped_topic(topic_id, project_id, user, db)
    db.delete(t)
    db.commit()
    return {"message": "Topic deleted"}


# ── Node management ───────────────────────────────────────────────────────────


@router.get("/{topic_id}/nodes")
def list_topic_nodes(
    topic_id: int,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Lists all nodes assigned to a specific topic.
    """
    t = get_scoped_topic(topic_id, project_id, user, db)
    return [serialize_topic_node(n) for n in t.nodes]


@router.post("/{topic_id}/nodes", status_code=201)
def attach_node(
    topic_id: int,
    data: TopicNodeAttach,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Adds a node (e.g., a code section or a Confluence document) to a topic.
    Used for grouping knowledge across repository boundaries.
    """
    t = get_scoped_topic(topic_id, project_id, user, db)
    assert_topic_node_project(data, t.project_id, db)
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
def detach_node(
    topic_id: int,
    node_id: int,
    project_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Removes a node link from a topic.
    """
    get_scoped_topic(topic_id, project_id, user, db)
    n = db.query(TopicNode).filter(TopicNode.id == node_id, TopicNode.topic_id == topic_id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Node link not found")
    db.delete(n)
    db.commit()
    return {"message": "Node removed"}
