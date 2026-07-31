from sqlalchemy import Boolean, Column, Integer, String, Text, Float, ForeignKey, DateTime, JSON, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID
import uuid

from models.crypto_types import EncryptedString

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, index=True, nullable=True)
    name = Column(String, nullable=True)
    # Bewusst String und NICHT EncryptedString: gefordert ist ein gesalzener Hash
    # (Argon2id), keine reversible Verschlüsselung. Das Feld darf in keinem
    # Serializer, Log oder Diagnose-Bundle auftauchen (CI-Job no-password-leak).
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, server_default="user")  # 'superuser' | 'user'
    is_active = Column(Boolean, nullable=False, server_default="true")
    must_change_password = Column(Boolean, nullable=False, server_default="false")
    failed_login_count = Column(Integer, nullable=False, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("TeamMembership", back_populates="team", cascade="all, delete-orphan")

class TeamMembership(Base):
    __tablename__ = "team_memberships"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="team_memberships")
    team = relationship("Team", back_populates="memberships")

    __table_args__ = (UniqueConstraint("user_id", "team_id", name="uq_team_memberships_user_team"),)

class Project(Base):
    """Oberster Container. Eine Git-Anbindung ist ein optionales Kind
    (KnowledgeSource mit type='Git'), genau wie Confluence oder ein Upload."""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    color = Column(String(7), nullable=True)

    team = relationship("Team", backref="projects")
    creator = relationship("User", backref="created_projects")
    memberships = relationship("ProjectMembership", back_populates="project", cascade="all, delete-orphan")
    access_requests = relationship("ProjectAccessRequest", back_populates="project", cascade="all, delete-orphan")

class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="member")  # "admin" | "member"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="project_memberships")
    project = relationship("Project", back_populates="memberships")

    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_project_memberships_user_project"),)

class ProjectAccessRequest(Base):
    __tablename__ = "project_access_requests"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="pending")  # "pending" | "approved" | "rejected"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="access_requests")
    user = relationship("User", backref="project_access_requests")

    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_access_requests_project_user"),)



class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String) # Git, Confluence, Jira, FolderWatch, WebDAV, Local
    url = Column(String, nullable=True)
    username = Column(String, nullable=True)
    token = Column(EncryptedString, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    spaces = Column(JSON, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String, default="pending") # pending, syncing, completed, error
    progress = Column(Integer, default=0)
    progress_message = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    sync_log = Column(Text, nullable=True)
    total_files = Column(Integer, nullable=True)
    parsed_files = Column(Integer, default=0)
    parse_started_at = Column(DateTime(timezone=True), nullable=True)
    parse_finished_at = Column(DateTime(timezone=True), nullable=True)
    estimated_finish_at = Column(DateTime(timezone=True), nullable=True)
    last_error_detail = Column(Text, nullable=True)
    # Auto-Sync-Intervall in Minuten (0 = nur manuell, kein automatischer Sync).
    # Der Beat-Task scan_pull_sources stößt eine Quelle erst wieder an, wenn seit
    # last_synced_at mindestens dieses Intervall vergangen ist.
    sync_interval_minutes = Column(Integer, nullable=False, server_default="60")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    # F-019: Branch ist ein eigenes Feld, nicht mehr in spaces-JSON versteckt. Zwei
    # Quellen auf dasselbe Repo mit verschiedenen Branches sind ausdrücklich erlaubt —
    # daher UNIQUE(project_id, url, branch) statt UNIQUE(url).
    branch = Column(String, nullable=True)
    # sha1 der normalisierten Repo-URL: mehrere Quellen teilen sich denselben
    # Bare-Mirror unter /repos/bare/<fingerprint>.git (ein 100-GB-Monorepo liegt
    # damit einmal auf Platte, egal wie viele Branches eingebunden sind).
    repo_fingerprint = Column(String, nullable=True, index=True)
    # NF-004: Wiederaufsetzpunkt eines abgebrochenen Syncs
    # {"last_commit": "...", "last_path": "...", "phase": "parse"}
    sync_cursor = Column(JSON, nullable=True)

    project = relationship("Project", backref="knowledge_sources")
    team = relationship("Team", backref="knowledge_sources")

    __table_args__ = (
        UniqueConstraint("project_id", "url", "branch", name="uq_knowledge_sources_project_url_branch"),
    )

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True)
    file_path = Column(String, index=True)
    content = Column(EncryptedString)
    start_line = Column(Integer)
    end_line = Column(Integer)
    metadata_json = Column(JSON) # Store symbols, language, etc.
    embedding = Column(Vector(1024)) # bge-m3

    project = relationship("Project", backref="document_chunks")
    knowledge_source = relationship("KnowledgeSource", backref="document_chunks")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    title = Column(String)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False, nullable=False)
    snapshot_json = Column(JSON, nullable=True)  # workspace/panel content-nav state, see buildWorkspaceSnapshot (frontend)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    project = relationship("Project")
    source = relationship("KnowledgeSource")
    owner = relationship("User")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role = Column(String) # user, assistant
    content = Column(EncryptedString)
    sources_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    feedback = Column(String, nullable=True)  # 'up' | 'down' | null, assistant messages only
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    session = relationship("ChatSession", back_populates="messages")

class CodeEntity(Base):
    """
    Ein geparstes COBOL-Objekt. Die Hierarchie Programm→Section→Paragraph bzw.
    Programm→DataItem wird über parent_id abgebildet (F-030).
    """
    __tablename__ = "code_entities"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True, index=True)
    file_path = Column(String, index=True)
    name = Column(String, index=True)
    # 'program'|'copybook'|'section'|'paragraph'|'data_item'|'file_fd'|'sql_table'|'sql_block'
    # v2 zusätzlich: 'jcl_job'|'jcl_step'
    type = Column(String, index=True)
    parent_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True)
    # Stabiler Schlüssel für Deep-Links: 'XAAOA.MAIN-SECTION.INIT-PARA'
    qualified_name = Column(String, nullable=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    # PIC-Klausel, Level, OCCURS/REDEFINES, SQL-Statement-Typ, Format (fixed/free)
    meta_json = Column(JSON, nullable=True)
    # Inkrementalität: unveränderte Datei → Entities/Kanten nicht neu schreiben
    content_hash = Column(String(64), nullable=True)

    children = relationship(
        "CodeEntity",
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "qualified_name", name="uq_code_entities_source_qname"),
        Index("ix_code_entities_source_type", "source_id", "type"),
    )


class CodeEdge(Base):
    """
    Gerichtete Beziehung zwischen zwei COBOL-Objekten (F-032).

    dst_name ist IMMER gesetzt, auch bei aufgelösten Kanten: beim inkrementellen
    Sync wird Programm A vor Programm B geparst, der CALL 'B' aus A ist zunächst
    unresolved. Sobald B da ist, löst ein Nachlauf-Pass die offenen Kanten über
    dst_name auf — ohne Reparse. Genau das macht die Monorepo-Ingestion
    wiederaufsetzbar (NF-004).
    """
    __tablename__ = "code_edges"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True, index=True)
    src_entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    dst_entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True)
    dst_name = Column(String, nullable=False, index=True)
    # v1: CALL | PERFORM | COPY | DEFINES | USES | READS | WRITES — v2: EXECUTES
    type = Column(String, nullable=False, index=True)
    # 'resolved' | 'unresolved' | 'dynamic'
    resolution = Column(String, nullable=False, server_default="unresolved")
    # Programmlokale Kantenarten (PERFORM/GO TO/USES) dürfen NUR innerhalb ihres
    # Programms aufgelöst werden: Paragraphennamen wie INIT-PARA existieren in
    # hunderten Programmen. Der Nachlauf-Pass filtert darüber, sonst entsteht ein
    # falsch verdrahteter Call-Graph (siehe docs/ENTSCHEIDUNGEN.md, E-1).
    scope_entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True)
    src_start_line = Column(Integer, nullable=False, server_default="0")
    src_end_line = Column(Integer, nullable=False, server_default="0")
    meta_json = Column(JSON, nullable=True)  # z.B. {"thru": "END-PARA"}, {"replacing": [...]}

    src_entity = relationship("CodeEntity", foreign_keys=[src_entity_id])
    dst_entity = relationship("CodeEntity", foreign_keys=[dst_entity_id])

    __table_args__ = (
        Index("ix_code_edges_src_type", "src_entity_id", "type"),
        Index("ix_code_edges_dst_type", "dst_entity_id", "type"),
        Index("ix_code_edges_dstname", "source_id", "dst_name"),
        Index("ix_code_edges_scope_name", "scope_entity_id", "dst_name"),
    )


class EntityDocLink(Base):
    __tablename__ = "entity_doc_links"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"))
    chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True)
    doc_title = Column(String, nullable=True)
    doc_url = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    link_type = Column(String, default="semantic")   # "semantic" | "manual"
    status = Column(String, default="pending", index=True)  # "pending" | "approved" | "rejected"
    context = Column(Text, nullable=True)            # LLM-Begründung oder manuelle Notiz
    created_by = Column(String, default="auto")      # "auto" | "user"
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", backref="entity_doc_links")
    entity = relationship("CodeEntity", backref="doc_links")
    chunk = relationship("DocumentChunk", backref="entity_links")

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    color = Column(String(20), default="indigo")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    nodes = relationship("TopicNode", back_populates="topic", cascade="all, delete-orphan", order_by="TopicNode.node_type")

class TopicNode(Base):
    __tablename__ = "topic_nodes"
    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    node_type = Column(String(30), nullable=False)  # 'project' | 'repository' | 'entity' | 'document' | 'knowledge_source'
    node_id = Column(Integer, nullable=False)
    node_label = Column(String(500), nullable=False)
    node_url = Column(Text, nullable=True)
    node_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    topic = relationship("Topic", back_populates="nodes")

class SourceScanFile(Base):
    """
    Datei-Journal je Wissensquelle — ersetzt die vier getrennten
    folder_/ifc_/dwg_/gaeb_scan_files-Tabellen des Templates.

    Dient gleichzeitig als:
      - Idempotenz-Journal für NF-004 ("Abbruch bei Datei n → Fortsetzung bei n+1")
      - Fehlerregister für F-029 (nicht parsebare Datei → Eintrag, kein Sync-Abbruch)
      - Datenquelle für den Datei-Zähler in F-014
    """
    __tablename__ = "source_scan_files"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    content_hash = Column(String(32), nullable=False)
    # 'ok' | 'fallback_text' | 'error' — 'fallback_text' = nicht parsebar, aber als
    # Volltext indiziert und damit weiterhin durchsuchbar (F-029).
    parse_status = Column(String, nullable=True)
    parse_error = Column(Text, nullable=True)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("source_id", "file_path", name="uq_source_scan_source_path"),)

    knowledge_source = relationship("KnowledgeSource", backref="scan_files")


class KnowledgeLink(Base):
    __tablename__ = "knowledge_links"
    id = Column(Integer, primary_key=True, index=True)
    
    # Source A (can be Code-Entity OR DocumentChunk)
    source_a_type = Column(String(20), nullable=False)          # 'entity' | 'document'
    source_a_entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True)
    source_a_chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True)
    source_a_title = Column(Text, nullable=False)
    source_a_url = Column(Text, nullable=True)
    source_a_source_type = Column(String(50), nullable=True)    # 'Git', 'Confluence', 'Jira', 'Local'
    
    # Source B (can be Code-Entity OR DocumentChunk)
    source_b_type = Column(String(20), nullable=False)          # 'entity' | 'document'
    source_b_entity_id = Column(Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True)
    source_b_chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True)
    source_b_title = Column(Text, nullable=False)
    source_b_url = Column(Text, nullable=True)
    source_b_source_type = Column(String(50), nullable=True)
    
    # Link Metadata
    score = Column(Float, nullable=True)
    link_type = Column(String(20), default="semantic")    # 'semantic', 'keyword', 'chat', 'manual'
    status = Column(String(20), default="pending", index=True) # 'pending', 'approved', 'rejected'
    context = Column(Text, nullable=True)                  # Why this link? (AI explanation)
    created_by = Column(String(50), default="auto")       # 'auto', 'user', 'chat'
    chat_session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_a_entity = relationship("CodeEntity", foreign_keys=[source_a_entity_id])
    source_a_chunk = relationship("DocumentChunk", foreign_keys=[source_a_chunk_id])
    source_b_entity = relationship("CodeEntity", foreign_keys=[source_b_entity_id])
    source_b_chunk = relationship("DocumentChunk", foreign_keys=[source_b_chunk_id])
    chat_session = relationship("ChatSession")

class LinkBuilderRun(Base):
    """
    One invocation of compute_entity_links (per-project) or compute_knowledge_links
    (global, project_id null). Persisted regardless of outcome — previously these
    tasks only surfaced crashes via logger.error with no queryable trace, making a
    silent failure indistinguishable from "ran fine, found nothing new".
    """
    __tablename__ = "link_builder_runs"
    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, nullable=False, index=True)  # "entity_links" | "knowledge_links"
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="pending", nullable=False)  # pending, running, completed, failed
    progress_message = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    links_created = Column(Integer, nullable=False, default=0)


class DiagnosticsRun(Base):
    """
    One invocation of the diagnostics-bundle Celery task (triggered via the
    Settings > Logs "Generate Diagnostics Bundle" button). Same
    pending/running/completed/failed shape as LinkBuilderRun — a crash here must
    be as visible as the failure it's meant to help diagnose.
    """
    __tablename__ = "diagnostics_runs"
    id = Column(Integer, primary_key=True, index=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="pending", nullable=False)  # pending, running, completed, failed
    progress_message = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    bundle_path = Column(String, nullable=True)  # tar.gz path under the shared ./repos mount
