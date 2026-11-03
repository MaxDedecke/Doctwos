"""Creation/validation of web knowledge sources, kept outside the large routing module."""

from fastapi import HTTPException
from api.serializers import serialize_source
from core.tracing import get_trace_id
from doctus_models.database import KnowledgeSource


def create_web_source(source, db, user):
    from api import knowledge_sources as api

    if source.type.lower() == "gitlabissues":
        from api.gitlab import gitlab_base

        if not source.url:
            raise HTTPException(status_code=400, detail="GitLab server URL is required")
        gitlab_base(source.url)
        if not source.token:
            raise HTTPException(status_code=400, detail="GitLab read token is required")
        ids = source.spaces.get("ids", []) if isinstance(source.spaces, dict) else source.spaces
        if (
            not isinstance(ids, list)
            or not ids
            or any(not str(value).strip() or str(value).upper() == "ALL" for value in ids)
        ):
            raise HTTPException(
                status_code=400,
                detail="Select explicit GitLab projects (IDs or namespace/project).",
            )
    team_id = api._resolve_team_id(source.project_id, db, user, source.team_id)
    api._check_knowledge_source_cap(source.project_id, db)
    db_source = KnowledgeSource(
        name=source.name,
        type=source.type,
        url=source.url,
        username=source.username,
        token=source.token,
        project_id=source.project_id,
        spaces=source.spaces,
        sync_interval_minutes=api._validate_sync_interval(source.sync_interval_minutes),
        context_note=api._validate_context_note(source.context_note),
        embedding_model=api._validate_embedding_model(source.embedding_model),
        team_id=team_id,
    )
    db.add(db_source)
    db.commit()
    db.refresh(db_source)

    # Einheitlicher Task für alle Web-Connector-Typen (Git/Confluence/Jira/WebDAV)
    if db_source.type and db_source.type.lower() in (
        "confluence",
        "jira",
        "gitlabissues",
        "webdav",
        "git",
    ):
        api.send_tracked_task(
            db, db_source, "process_knowledge_source", [db_source.id], {"trace_id": get_trace_id()}
        )

    return serialize_source(db_source)
