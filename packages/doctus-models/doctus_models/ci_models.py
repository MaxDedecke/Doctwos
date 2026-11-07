"""Source-scoped CI credentials and immutable terminal build reports."""

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    DateTime,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index,
    func,
)
from .model_base import Base


class CIBuildToken(Base):
    __tablename__ = "ci_build_tokens"
    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    token_prefix = Column(String(20), nullable=False)
    repository = Column(String(64), nullable=False)
    branch = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class CIBuildRun(Base):
    __tablename__ = "ci_build_runs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False
    )
    token_id = Column(Integer, ForeignKey("ci_build_tokens.id", ondelete="SET NULL"), nullable=True)
    repository = Column(String(64), nullable=False)
    branch = Column(String(256), nullable=False)
    commit = Column(String(64), nullable=False)
    provider = Column(String(20), nullable=False)
    run_id = Column(String(200), nullable=False)
    attempt = Column(BigInteger, nullable=False)
    job_name = Column(String(200), nullable=False)
    variant = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False)
    pipeline_url = Column(String(2000), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    identity_hash = Column(String(64), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    summary = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "identity_hash", name="uq_ci_build_run_identity"),
        Index("ix_ci_build_runs_source_commit", "project_id", "source_id", "commit", "finished_at"),
    )
