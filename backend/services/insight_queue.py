"""Indexed search and SQL-side filtering of a bounded insight worklist."""

from datetime import datetime, timezone
from sqlalchemy import func, literal_column, text, case
from doctus_models.database import Insight, ProjectMembership, TeamMembership, Project, User

REVIEW_REQUIRED = text("""
(insights.status IN ('draft','outdated') OR
 (insights.status = 'verified' AND (
   ((insights.version_bindings IS NULL OR insights.version_bindings::jsonb = '[]'::jsonb) AND EXISTS
      (SELECT 1 FROM knowledge_sources s WHERE s.project_id=insights.project_id AND lower(s.type)='git'))
   OR EXISTS (
     SELECT 1 FROM jsonb_array_elements(COALESCE(insights.version_bindings::jsonb,'[]'::jsonb)) b
     LEFT JOIN knowledge_sources s ON s.id=(b->>'source_id')::int AND s.project_id=insights.project_id
     WHERE s.id IS NULL OR s.sync_status IS DISTINCT FROM 'completed' OR
       (b->>'kind'='git' AND (
          s.sync_cursor->>'last_commit' IS DISTINCT FROM b->>'commit'
          OR s.branch IS DISTINCT FROM b->>'branch'
          OR (s.repo_fingerprint IS NOT NULL AND s.repo_fingerprint IS DISTINCT FROM b->>'repository')
       ))
   )
 )))
""")


def search_vector():
    return func.to_tsvector(
        literal_column("'simple'"),
        func.coalesce(Insight.title, "") + " " + func.coalesce(Insight.content, ""),
    )


def search_filter(query, q):
    tsquery = func.websearch_to_tsquery(literal_column("'simple'"), q)
    vector = search_vector()
    return query.filter(vector.op("@@")(tsquery)), func.ts_rank_cd(vector, tsquery)


def worklist_query(
    db,
    project_id,
    user,
    *,
    q="",
    status=None,
    mine=False,
    unassigned=False,
    reviewer=False,
    needs_review=False,
    priority=None,
):
    query = db.query(Insight).filter(Insight.project_id == project_id)
    rank = None
    if q:
        query, rank = search_filter(query, q)
    if status:
        query = query.filter(Insight.status == status)
    if unassigned:
        query = query.filter(Insight.owner_id.is_(None))
    if mine:
        query = query.filter(Insight.owner_id == user.id)
    if reviewer:
        query = query.filter(Insight.reviewer_id == user.id)
    if priority is not None:
        query = query.filter(Insight.priority == priority)
    if needs_review:
        query = query.filter(REVIEW_REQUIRED)
    return query, rank


def order_worklist(query, rank=None):
    now = datetime.now(timezone.utc)
    order = [rank.desc()] if rank is not None else []
    return query.order_by(
        *order,
        case((Insight.due_at < now, 0), else_=1),
        Insight.priority.desc(),
        case(
            (Insight.status == "outdated", 0),
            (Insight.status == "draft", 1),
            (Insight.status == "verified", 2),
            else_=3,
        ),
        Insight.due_at.asc().nullslast(),
        Insight.updated_at.asc(),
        Insight.id.asc(),
    )


def assignment_candidates(db, project_id):
    project = db.get(Project, project_id)
    return (
        db.query(User, ProjectMembership.role)
        .join(
            ProjectMembership,
            ProjectMembership.user_id == User.id,
        )
        .join(
            TeamMembership,
            (TeamMembership.user_id == User.id) & (TeamMembership.team_id == project.team_id),
        )
        .filter(
            ProjectMembership.project_id == project_id,
            User.is_active.is_(True),
        )
        .order_by(User.username)
        .limit(501)
        .all()
    )


def valid_assignee(db, project_id, user_id, reviewer=False):
    if user_id is None:
        return True
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return False
    project = db.get(Project, project_id)
    member = (
        db.query(ProjectMembership)
        .join(
            TeamMembership,
            (TeamMembership.user_id == ProjectMembership.user_id)
            & (TeamMembership.team_id == project.team_id),
        )
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id)
        .first()
    )
    return bool(member and (not reviewer or member.role == "admin")) or user.role == "superuser"
