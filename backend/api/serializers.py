"""
backend/api/serializers.py
===========================
Response-Serialisierungsfunktionen für Datenbank-Objekte.

Zentralisiert, damit alle Router dasselbe Format zurückgeben.
Änderung am Response-Format: hier anpassen, gilt überall.
"""

from models.database import (
    CodeEntity, EntityDocLink, KnowledgeSource, KnowledgeLink, Topic, TopicNode,
    Project
)


def serialize_project(p: Project, serialize_repo_info: bool = True) -> dict:
    if not p:
        return None
    
    git_source = None
    if serialize_repo_info:
        try:
            sources = p.knowledge_sources
        except Exception:
            sources = []
        git_source = next((s for s in sources if s.type == "Git"), None)

    res = {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "team_id": p.team_id,
        "creator_id": p.creator_id,
        "is_archived": p.is_archived,
        "color": p.color,
        "jurisdiction": p.jurisdiction,
        "regulation_date": p.regulation_date.isoformat() if p.regulation_date else None,
        "regulation_snapshot_id": p.regulation_snapshot_id,
        "repository": None
    }
    if git_source:
        status = git_source.sync_status
        if status == "syncing":
            status = "parsing"
        
        spaces = git_source.spaces or {}
        res.update({
            "status": status,
            "progress": git_source.progress,
            "progress_message": git_source.progress_message,
            "url": git_source.url,
            "branch": spaces.get("branch", "main"),
            "last_commit_hash": spaces.get("last_commit_hash"),
            "repo_id": git_source.id,
        })
    else:
        res.update({
            "status": None,
            "progress": None,
            "progress_message": None,
            "url": None,
            "branch": None,
            "last_commit_hash": None,
            "repo_id": None,
        })
    return res


def serialize_source(s: KnowledgeSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "type": s.type,
        "url": s.url,
        "username": s.username,
        "token": "***" if s.token else None,
        "project_id": s.project_id,
        "repo_id": s.project_id,
        "branch": s.branch,
        "spaces": s.spaces,
        "last_synced_at": s.last_synced_at.isoformat() if s.last_synced_at else None,
        "sync_status": s.sync_status,
        "progress": s.progress,
        "progress_message": s.progress_message,
        "last_error": s.last_error,
        "sync_log": s.sync_log,
        "sync_interval_minutes": s.sync_interval_minutes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "team_id": s.team_id,
        "total_files": s.total_files,
        "parsed_files": s.parsed_files,
        "parse_started_at": s.parse_started_at.isoformat() if s.parse_started_at else None,
        "parse_finished_at": s.parse_finished_at.isoformat() if s.parse_finished_at else None,
        "estimated_finish_at": s.estimated_finish_at.isoformat() if s.estimated_finish_at else None,
        "last_error_detail": s.last_error_detail,
    }


def serialize_link(link: EntityDocLink, entity: CodeEntity = None) -> dict:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "entity_id": link.entity_id,
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "type": entity.type,
            "file_path": entity.file_path,
            "start_line": entity.start_line,
            "end_line": entity.end_line,
        } if entity else None,
        "chunk_id": link.chunk_id,
        "doc_title": link.doc_title,
        "doc_url": link.doc_url,
        "source_type": link.source_type,
        "score": link.score,
        "link_type": link.link_type,
        "status": link.status,
        "context": link.context,
        "created_by": link.created_by,
        "reviewed_at": link.reviewed_at.isoformat() if link.reviewed_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def serialize_topic(t: Topic) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "color": t.color,
        "node_count": len(t.nodes),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def serialize_topic_node(n: TopicNode) -> dict:
    return {
        "id": n.id,
        "topic_id": n.topic_id,
        "node_type": n.node_type,
        "node_id": n.node_id,
        "node_label": n.node_label,
        "node_url": n.node_url,
        "node_meta": n.node_meta,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def serialize_knowledge_link(link: KnowledgeLink) -> dict:
    return {
        "id": link.id,
        "source_a": {
            "type": link.source_a_type,
            "entity_id": link.source_a_entity_id,
            "chunk_id": link.source_a_chunk_id,
            "title": link.source_a_title,
            "url": link.source_a_url,
            "source_type": link.source_a_source_type,
        },
        "source_b": {
            "type": link.source_b_type,
            "entity_id": link.source_b_entity_id,
            "chunk_id": link.source_b_chunk_id,
            "title": link.source_b_title,
            "url": link.source_b_url,
            "source_type": link.source_b_source_type,
        },
        "score": link.score,
        "link_type": link.link_type,
        "status": link.status,
        "context": link.context,
        "created_by": link.created_by,
        "chat_session_id": link.chat_session_id,
        "reviewed_at": link.reviewed_at.isoformat() if link.reviewed_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }
