from fastapi import HTTPException

from doctus_models.database import CodeEntity, DocumentChunk, KnowledgeSource, Topic
from services.link_project_scope import assert_link_project


def get_scoped_topic(topic_id, project_id, user, db):
    if project_id is not None:
        assert_link_project(project_id, user, db)
    query = db.query(Topic).filter(Topic.id == topic_id)
    if project_id is not None:
        query = query.filter(Topic.project_id == project_id)
    topic = query.first()
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def assert_topic_node_project(node, project_id, db):
    if project_id is None:
        return
    if node.node_type in {"project", "repository"}:
        owner = node.node_id
    else:
        model = {
            "entity": CodeEntity,
            "document": DocumentChunk,
            "knowledge_source": KnowledgeSource,
        }.get(node.node_type)
        row = db.get(model, node.node_id) if model else None
        owner = row.project_id if row else None
        if (
            row is not None
            and owner is None
            and node.node_type != "knowledge_source"
            and row.source_id
        ):
            source = db.get(KnowledgeSource, row.source_id)
            owner = source.project_id if source else None
    if owner != project_id:
        raise HTTPException(
            status_code=422, detail="Der Eintrag muss zum Projekt des Themas gehören"
        )
