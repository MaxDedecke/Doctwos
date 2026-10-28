"""Project insight nodes and their scoped evidence relationships."""

from models.database import CodeEntity, DocumentChunk, Insight


def append_insight_graph(db, project_ids, nodes, edges, ensure_file, doc_node):
    if not project_ids:
        return
    insights = (
        db.query(Insight)
        .filter(Insight.project_id.in_(project_ids))
        .order_by(Insight.id)
        .limit(1000)
        .all()
    )
    for insight in insights:
        node_id = f"insight:{insight.id}"
        nodes[node_id] = {
            "id": node_id,
            "type": "insight",
            "label": insight.title,
            "project_id": insight.project_id,
            "content": insight.content,
            "status": insight.status,
            "evidence": insight.evidence_json or [],
        }
        for index, evidence in enumerate(insight.evidence_json or []):
            target_id = None
            entity_id = evidence.get("entity_id")
            if entity_id is not None:
                entity = (
                    db.query(CodeEntity)
                    .filter(CodeEntity.id == entity_id, CodeEntity.project_id == insight.project_id)
                    .first()
                )
                if entity:
                    target_id = ensure_file(nodes, entity)
            path = evidence.get("file")
            if target_id is None and isinstance(path, str):
                query = db.query(DocumentChunk).filter(
                    DocumentChunk.project_id == insight.project_id, DocumentChunk.file_path == path
                )
                if evidence.get("source_id") is not None:
                    query = query.filter(DocumentChunk.source_id == evidence["source_id"])
                chunk = query.order_by(DocumentChunk.id).first()
                if chunk:
                    existing = next(
                        (
                            n
                            for n in nodes.values()
                            if n.get("project_id") == chunk.project_id
                            and n.get("source_id") == chunk.source_id
                            and n.get("file_path") == path
                        ),
                        None,
                    )
                    node = existing or doc_node(path, None, None, chunk)
                    nodes.setdefault(node["id"], node)
                    target_id = node["id"]
            if target_id:
                edges.append(
                    {
                        "id": f"insight-evidence:{insight.id}:{index}",
                        "source": node_id,
                        "target": target_id,
                        "link_type": "evidence",
                        "direction": "directed",
                        "score": None,
                        "context": "Evidence snapshot",
                        "meta": evidence,
                    }
                )
