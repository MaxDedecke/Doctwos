"""Reviewed knowledge and its team workflow, using the shared ORM registry."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    CheckConstraint,
    Index,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import relationship, backref
from pgvector.sqlalchemy import Vector
from .model_base import Base


class Insight(Base):
    """A human-owned, evidence-backed project finding.

    Source provenance on a chunk or code edge says where a fact came from; it
    does not establish that a user-facing conclusion has been reviewed.  An
    Insight is deliberately separate from both link-review tables so its
    four-eyes approval remains auditable and cannot be inferred from an
    approved semantic link.
    """

    __tablename__ = "insights"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(240), nullable=False)
    content = Column(Text, nullable=False)
    # chat | code | process: the user workflow which produced the draft.
    origin_kind = Column(String(20), nullable=False)
    # Immutable locator/snapshot supplied by that workflow (chat message,
    # source citations, CodeEntity or process edge IDs).
    evidence_json = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    # Keep the audit trail internally consistent: a verified record cannot
    # survive deletion of its verifier with a NULL reviewer. Accounts with
    # authored insights therefore require explicit archival handling.
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    outdated_at = Column(DateTime(timezone=True), nullable=True)
    outdated_source_ids = Column(JSON, nullable=True)
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    review_history = Column(JSON, nullable=False, default=list, server_default="[]")
    version_bindings = Column(JSON, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    priority = Column(Integer, nullable=False, default=1, server_default="1")
    work_revision = Column(Integer, nullable=False, default=1, server_default="1")
    workflow_history = Column(JSON, nullable=False, default=list, server_default="[]")
    due_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    project = relationship("Project", backref=backref("insights", passive_deletes=True))
    created_by = relationship("User", foreign_keys=[created_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index(
            "ix_insights_search",
            text("to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_insights_evidence_gin", text("(evidence_json::jsonb)"), postgresql_using="gin"
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_insights_bindings_gin", text("(version_bindings::jsonb)"), postgresql_using="gin"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("priority BETWEEN 0 AND 3", name="ck_insights_priority"),
        Index("ix_insights_worklist", "project_id", "status", "priority", "due_at", "id"),
        Index("ix_insights_owner", "project_id", "owner_id", "id"),
        CheckConstraint(
            "origin_kind IN ('chat', 'code', 'process')", name="ck_insights_origin_kind"
        ),
        CheckConstraint(
            "status IN ('draft', 'verified', 'outdated', 'rejected')", name="ck_insights_status"
        ),
        CheckConstraint(
            "(status IN ('draft', 'rejected') AND verified_by_id IS NULL AND verified_at IS NULL) OR "
            "(status IN ('verified', 'outdated') AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_insights_verification_state",
        ),
    )


class InsightNotification(Base):
    __tablename__ = "insight_notifications"
    id = Column(Integer, primary_key=True)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(40), nullable=False)
    cycle_key = Column(String(80), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint(
            "insight_id", "user_id", "kind", "cycle_key", name="uq_insight_notification_cycle"
        ),
        Index("ix_insight_notifications_inbox", "project_id", "user_id", "read_at", "id"),
    )


class InsightEmbedding(Base):
    __tablename__ = "insight_embeddings"
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="CASCADE"), primary_key=True)
    profile_key = Column(String(64), nullable=False)
    content_hash = Column(String(64), nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        Index("ix_insight_embeddings_profile", "profile_key"),
        Index("ix_insight_embeddings_scope", "project_id", "profile_key"),
        Index(
            "ix_insight_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
    )
