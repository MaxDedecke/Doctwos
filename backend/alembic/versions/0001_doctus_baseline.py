"""doctus baseline schema

Eine einzige Baseline statt der 32 Condo-Migrationen: Doctus startet auf einer
leeren Datenbank, eine Migrationskette aus der Template-Historie hätte nur
Tabellen angelegt, die dieselbe Kette später wieder droppt.

Enthält gegenüber dem Template:
  - users mit lokaler Anmeldung (F-001/F-004/F-005) statt OIDC-`sub`
  - code_entities COBOL-tauglich + code_edges (F-030/F-032)
  - source_scan_files statt vier getrennter Scan-Tabellen (NF-004/F-029)
  - knowledge_sources.branch/repo_fingerprint/sync_cursor (F-019/NF-004)
Entfallen: alle compliance_*/regulation_*-Tabellen, ifc/dwg/gaeb_scan_files.

Revision ID: 0001_doctus_baseline
Revises:
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001_doctus_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_teams_id", "teams", ["id"])
    op.create_index("ix_teams_name", "teams", ["name"], unique=True)

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_team_memberships_id", "team_memberships", ["id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("color", sa.String(length=7), nullable=True),
    )
    op.create_index("ix_projects_id", "projects", ["id"])
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_team_id", "projects", ["team_id"])

    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(), server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "project_id", name="uq_project_memberships_user_project"),
    )
    op.create_index("ix_project_memberships_id", "project_memberships", ["id"])

    op.create_table(
        "project_access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_access_requests_project_user"),
    )
    op.create_index("ix_project_access_requests_id", "project_access_requests", ["id"])

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String()),
        sa.Column("type", sa.String()),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("token", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("spaces", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(), server_default="pending"),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("progress_message", sa.String(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sync_log", sa.Text(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=True),
        sa.Column("parsed_files", sa.Integer(), server_default="0"),
        sa.Column("parse_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parse_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_finish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_detail", sa.Text(), nullable=True),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("repo_fingerprint", sa.String(), nullable=True),
        sa.Column("sync_cursor", sa.JSON(), nullable=True),
        # F-019: dasselbe Repo darf mehrfach eingebunden werden, solange sich der
        # Branch unterscheidet — deshalb NICHT UNIQUE(url).
        sa.UniqueConstraint("project_id", "url", "branch", name="uq_knowledge_sources_project_url_branch"),
    )
    op.create_index("ix_knowledge_sources_id", "knowledge_sources", ["id"])
    op.create_index("ix_knowledge_sources_name", "knowledge_sources", ["name"])
    op.create_index("ix_knowledge_sources_team_id", "knowledge_sources", ["team_id"])
    op.create_index("ix_knowledge_sources_repo_fingerprint", "knowledge_sources", ["repo_fingerprint"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("file_path", sa.String()),
        sa.Column("content", sa.Text()),
        sa.Column("start_line", sa.Integer()),
        sa.Column("end_line", sa.Integer()),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("embedding", Vector(1024)),
    )
    op.create_index("ix_document_chunks_id", "document_chunks", ["id"])
    op.create_index("ix_document_chunks_file_path", "document_chunks", ["file_path"])
    op.create_index("ix_document_chunks_project_file", "document_chunks", ["project_id", "file_path"])
    # Übernommen aus b1c2d3e4f5a6 (NF-010): bge-m3 = 1024 Dimensionen, Cosine.
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String()),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("snapshot_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_id", "chat_sessions", ["id"])
    op.create_index("ix_chat_sessions_uuid", "chat_sessions", ["uuid"], unique=True)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE")),
        sa.Column("role", sa.String()),
        sa.Column("content", sa.Text()),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_id", "chat_messages", ["id"])

    op.create_table(
        "code_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("file_path", sa.String()),
        sa.Column("name", sa.String()),
        sa.Column("type", sa.String()),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("qualified_name", sa.String(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=True),
        sa.Column("end_line", sa.Integer(), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("source_id", "qualified_name", name="uq_code_entities_source_qname"),
    )
    op.create_index("ix_code_entities_id", "code_entities", ["id"])
    op.create_index("ix_code_entities_source_id", "code_entities", ["source_id"])
    op.create_index("ix_code_entities_file_path", "code_entities", ["file_path"])
    op.create_index("ix_code_entities_name", "code_entities", ["name"])
    op.create_index("ix_code_entities_type", "code_entities", ["type"])
    op.create_index("ix_code_entities_parent_id", "code_entities", ["parent_id"])
    op.create_index("ix_code_entities_source_type", "code_entities", ["source_id", "type"])

    op.create_table(
        "code_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True),
        sa.Column("src_entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dst_entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("dst_name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("resolution", sa.String(), nullable=False, server_default="unresolved"),
        sa.Column("scope_entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("src_start_line", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("src_end_line", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_code_edges_id", "code_edges", ["id"])
    op.create_index("ix_code_edges_project_id", "code_edges", ["project_id"])
    op.create_index("ix_code_edges_source_id", "code_edges", ["source_id"])
    op.create_index("ix_code_edges_src_entity_id", "code_edges", ["src_entity_id"])
    op.create_index("ix_code_edges_dst_entity_id", "code_edges", ["dst_entity_id"])
    op.create_index("ix_code_edges_dst_name", "code_edges", ["dst_name"])
    op.create_index("ix_code_edges_type", "code_edges", ["type"])
    op.create_index("ix_code_edges_scope_entity_id", "code_edges", ["scope_entity_id"])
    op.create_index("ix_code_edges_src_type", "code_edges", ["src_entity_id", "type"])
    op.create_index("ix_code_edges_dst_type", "code_edges", ["dst_entity_id", "type"])
    op.create_index("ix_code_edges_dstname", "code_edges", ["source_id", "dst_name"])
    op.create_index("ix_code_edges_scope_name", "code_edges", ["scope_entity_id", "dst_name"])

    op.create_table(
        "entity_doc_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("doc_title", sa.String(), nullable=True),
        sa.Column("doc_url", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("link_type", sa.String(), server_default="semantic"),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), server_default="auto"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_entity_doc_links_id", "entity_doc_links", ["id"])
    op.create_index("ix_entity_doc_links_status", "entity_doc_links", ["status"])

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=20), server_default="indigo"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_topics_id", "topics", ["id"])
    op.create_index("ix_topics_name", "topics", ["name"])

    op.create_table(
        "topic_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(length=30), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("node_label", sa.String(length=500), nullable=False),
        sa.Column("node_url", sa.Text(), nullable=True),
        sa.Column("node_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_topic_nodes_id", "topic_nodes", ["id"])

    op.create_table(
        "source_scan_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=32), nullable=False),
        sa.Column("parse_status", sa.String(), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "file_path", name="uq_source_scan_source_path"),
    )
    op.create_index("ix_source_scan_files_id", "source_scan_files", ["id"])
    op.create_index("ix_source_scan_files_source_id", "source_scan_files", ["source_id"])

    op.create_table(
        "knowledge_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_a_type", sa.String(length=20), nullable=False),
        sa.Column("source_a_entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_a_chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_a_title", sa.Text(), nullable=False),
        sa.Column("source_a_url", sa.Text(), nullable=True),
        sa.Column("source_a_source_type", sa.String(length=50), nullable=True),
        sa.Column("source_b_type", sa.String(length=20), nullable=False),
        sa.Column("source_b_entity_id", sa.Integer(), sa.ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_b_chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_b_title", sa.Text(), nullable=False),
        sa.Column("source_b_url", sa.Text(), nullable=True),
        sa.Column("source_b_source_type", sa.String(length=50), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("link_type", sa.String(length=20), server_default="semantic"),
        sa.Column("status", sa.String(length=20), server_default="pending"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=50), server_default="auto"),
        sa.Column("chat_session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_knowledge_links_id", "knowledge_links", ["id"])
    op.create_index("ix_knowledge_links_status", "knowledge_links", ["status"])

    op.create_table(
        "link_builder_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("progress_message", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("links_created", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_link_builder_runs_id", "link_builder_runs", ["id"])
    op.create_index("ix_link_builder_runs_task_type", "link_builder_runs", ["task_type"])
    op.create_index("ix_link_builder_runs_project_id", "link_builder_runs", ["project_id"])

    op.create_table(
        "diagnostics_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("triggered_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("progress_message", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bundle_path", sa.String(), nullable=True),
    )
    op.create_index("ix_diagnostics_runs_id", "diagnostics_runs", ["id"])
    op.create_index("ix_diagnostics_runs_triggered_by_user_id", "diagnostics_runs", ["triggered_by_user_id"])


def downgrade() -> None:
    for table in (
        "diagnostics_runs",
        "link_builder_runs",
        "knowledge_links",
        "source_scan_files",
        "topic_nodes",
        "topics",
        "entity_doc_links",
        "code_edges",
        "code_entities",
        "chat_messages",
        "chat_sessions",
        "document_chunks",
        "knowledge_sources",
        "project_access_requests",
        "project_memberships",
        "projects",
        "team_memberships",
        "teams",
        "users",
    ):
        op.drop_table(table)
