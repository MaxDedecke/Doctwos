from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Integer,
    String,
    Text,
    Float,
    ForeignKey,
    DateTime,
    JSON,
    UniqueConstraint,
    Index,
    event,
)
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
    # NULL nur für per OIDC angelegte Nutzer (core/users.py::create_oidc_user) —
    # die haben kein lokales Passwort, das gehasht werden könnte (E-12).
    password_hash = Column(String, nullable=True)
    # Feste IdP-Nutzerkennung ('sub'-Claim) für per SSO angelegte Konten. NULL bei
    # lokalen Konten. Dient als alleiniger Schlüssel für den erneuten Login über
    # OIDC — bewusst nicht die E-Mail (kann sich beim IdP ändern/wiederverwendet
    # werden), siehe E-12.
    oidc_subject = Column(String, unique=True, index=True, nullable=True)
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

    memberships = relationship(
        "TeamMembership", back_populates="team", cascade="all, delete-orphan"
    )


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
    # Default-deny Opt-in: Code-Analyse-Objekte (CodeEntity/Callgraph) dieses Projekts
    # sind außerhalb des eigenen Projekt-Kontexts (Allgemein-Suche, Allgemein-Graph-View,
    # oder aus einem ANDEREN Projekt heraus) nur sichtbar, wenn dieses Flag gesetzt ist —
    # siehe core/projects.py::assert_project_code_visible_in_context. Innerhalb des
    # eigenen Projekt-Kontexts (Code-Editor, projektgebundene Panels) bleibt der Zugriff
    # von diesem Flag unberührt.
    expose_code_analysis_globally = Column(Boolean, default=False, nullable=False)

    team = relationship("Team", backref="projects")
    creator = relationship("User", backref="created_projects")
    memberships = relationship(
        "ProjectMembership", back_populates="project", cascade="all, delete-orphan"
    )
    access_requests = relationship(
        "ProjectAccessRequest", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="member")  # "admin" | "member"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="project_memberships")
    project = relationship("Project", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_project_memberships_user_project"),
    )


class ProjectAccessRequest(Base):
    __tablename__ = "project_access_requests"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="pending")  # "pending" | "approved" | "rejected"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="access_requests")
    user = relationship("User", backref="project_access_requests")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_access_requests_project_user"),
    )


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
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
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

    project = relationship("Project", backref=backref("insights", passive_deletes=True))
    created_by = relationship("User", foreign_keys=[created_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        CheckConstraint("origin_kind IN ('chat', 'code', 'process')", name="ck_insights_origin_kind"),
        CheckConstraint("status IN ('draft', 'verified')", name="ck_insights_status"),
        CheckConstraint(
            "(status = 'draft' AND verified_by_id IS NULL AND verified_at IS NULL) OR "
            "(status = 'verified' AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_insights_verification_state",
        ),
    )


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    type = Column(String)  # Git, Confluence, Jira, FolderWatch, WebDAV, Local
    url = Column(String, nullable=True)
    username = Column(String, nullable=True)
    token = Column(EncryptedString, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    spaces = Column(JSON, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String, default="pending")  # pending, syncing, completed, error, cancelled
    celery_task_id = Column(String(255), nullable=True)
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
    # Frei editierbare Fachwissen-Notiz zu dieser Quelle (z.B. Kunden-Jargon wie
    # "diese Confluence-Seiten heißen bei uns Schlüsselbeschreibungen und
    # bedeuten ..."). Fließt bei Chat-Anfragen in dieser Quelle/diesem Projekt
    # als vertrauenswürdiger Text in den System-Prompt ein (siehe
    # backend/services/source_context.py) — kein RAG-Chunk, wird nicht embeddet.
    context_note = Column(Text, nullable=True)
    # Embedding-Modell, mit dem diese Quelle indiziert wird. NULL bei alten
    # Quellen bedeutet den Deployment-Default (OLLAMA_EMBED_MODEL).
    embedding_model = Column(String, nullable=True)
    # O-177: exact project/source scope used by a cross-source run.
    scope_json = Column(JSON, nullable=True)

    # passive_deletes=True: project_id/team_id tragen bereits ondelete="CASCADE"
    # in der DB (siehe oben). Ohne dieses Flag laedt SQLAlchemy beim Loeschen
    # eines Project/Team stattdessen die abhaengigen KnowledgeSource-Zeilen und
    # setzt project_id/team_id per UPDATE auf NULL statt die DB-CASCADE greifen
    # zu lassen — project_id ist nullable, das UPDATE gelingt lautlos und
    # hinterlaesst eine verwaiste Quelle (gefunden bei AP-9, delete_project()).
    project = relationship("Project", backref=backref("knowledge_sources", passive_deletes=True))
    team = relationship("Team", backref=backref("knowledge_sources", passive_deletes=True))

    __table_args__ = (
        UniqueConstraint(
            "project_id", "url", "branch", name="uq_knowledge_sources_project_url_branch"
        ),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True
    )
    file_path = Column(String, index=True)
    content = Column(EncryptedString)
    start_line = Column(Integer)
    end_line = Column(Integer)
    metadata_json = Column(JSON)  # Store symbols, language, etc.
    # Deliberately unbounded: the serving model determines the vector length.
    # Every retrieval query filters ``embedding_dimension`` before calculating
    # a distance, so vectors from different spaces are never compared.
    embedding = Column(Vector)
    embedding_dimension = Column(Integer, nullable=True, index=True)
    # Persistiert neben dem Vektor, welchem Modell er entstammt. Das verhindert,
    # dass semantisch inkompatible Modelle trotz gleicher Dimension vermischt
    # werden. NULL bei Altbeständen wird als Deployment-Default behandelt.
    embedding_model = Column(String, nullable=True)
    # O-180: fingerprint and revision used to decide whether link candidates
    # need to be recalculated after an incremental source sync.
    content_hash = Column(String(64), nullable=True, index=True)
    link_revision = Column(Integer, nullable=False, server_default="0")

    # passive_deletes=True: siehe Begruendung bei KnowledgeSource.project oben,
    # derselbe Mechanismus wuerde sonst beim Loeschen eines Projekts/einer
    # Wissensquelle die Embeddings verwaist statt kaskadierend geloescht lassen.
    project = relationship("Project", backref=backref("document_chunks", passive_deletes=True))
    knowledge_source = relationship(
        "KnowledgeSource", backref=backref("document_chunks", passive_deletes=True)
    )

    # Beide Indizes stehen so schon in der Baseline-Migration. Sie gehören
    # trotzdem hierher: was das ORM nicht kennt, will `alembic revision
    # --autogenerate` beim nächsten Mal löschen — und ein stillschweigend
    # entfernter HNSW-Index degradiert die Suche zum Full Scan, ohne Fehler.
    __table_args__ = (Index("ix_document_chunks_project_file", "project_id", "file_path"),)


@event.listens_for(DocumentChunk.embedding, "set")
def _set_embedding_dimension(target, value, oldvalue, initiator):
    target.embedding_dimension = len(value) if value is not None else None


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    title = Column(String)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True
    )
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_public = Column(Boolean, default=False, nullable=False)
    snapshot_json = Column(
        JSON, nullable=True
    )  # workspace/panel content-nav state, see buildWorkspaceSnapshot (frontend)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    project = relationship("Project")
    source = relationship("KnowledgeSource")
    owner = relationship("User")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role = Column(String)  # user, assistant
    content = Column(EncryptedString)
    sources_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    feedback = Column(String, nullable=True)  # 'up' | 'down' | null, assistant messages only
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    session = relationship("ChatSession", back_populates="messages")


class ChatLinkFeedbackSignal(Base):
    """Auditierbares Downvote-Signal für einen aus einer Chat-Antwort zitierten Link.

    ``link_type``/``link_id`` sind absichtlich ein generischer Verweis: Ein Signal
    kann sowohl einen EntityDocLink als auch einen KnowledgeLink betreffen. Beim
    Zurücknehmen eines Downvotes bleibt der Datensatz für die Nachvollziehbarkeit
    erhalten, zählt aber ab ``revoked_at`` nicht mehr zur Eskalationsregel.
    """

    __tablename__ = "chat_link_feedback_signals"
    id = Column(Integer, primary_key=True, index=True)
    chat_message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chat_session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    link_type = Column(String(30), nullable=False)  # 'entity_doc' | 'knowledge'
    link_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    message = relationship("ChatMessage", backref="link_feedback_signals")
    session = relationship("ChatSession")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "chat_message_id", "link_type", "link_id", name="uq_chat_link_feedback_signal"
        ),
        Index("ix_chat_link_feedback_active", "link_type", "link_id", "revoked_at", "created_at"),
    )


class ChatFeedbackDiagnosticSettings(Base):
    """Deployment-weit gültiges, explizites Admin-Opt-in für O-088."""

    __tablename__ = "chat_feedback_diagnostic_settings"
    id = Column(Integer, primary_key=True)
    collection_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    support_export_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    retention_days = Column(Integer, nullable=False, default=90, server_default="90")
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    updated_by = relationship("User")


class AISettings(Base):
    """Deployment-wide AI profile, editable by administrators in the UI.

    The worker reads this row directly from the shared database, so changing an
    endpoint or model does not require changing an environment variable or
    restarting a container. API keys use the same at-rest encryption as source
    tokens and document content.
    """

    __tablename__ = "ai_settings"
    id = Column(Integer, primary_key=True)
    llm_provider = Column(String(32), nullable=False, server_default="ollama")
    llm_model = Column(String, nullable=False, server_default="disabled")
    llm_base_url = Column(String, nullable=True)
    llm_api_key = Column(EncryptedString, nullable=True)
    embedding_provider = Column(String(32), nullable=False, server_default="ollama")
    embedding_model = Column(String, nullable=False, server_default="bge-m3")
    embedding_base_url = Column(String, nullable=True)
    embedding_api_key = Column(EncryptedString, nullable=True)
    embedding_dimension = Column(Integer, nullable=False, server_default="1024")
    embedding_context_length = Column(Integer, nullable=False, server_default="8192")
    llm_context_length = Column(Integer, nullable=False, server_default="8192")
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    active_profile_id = Column(
        Integer, ForeignKey("ai_profiles.id", ondelete="SET NULL"), nullable=True
    )
    active_embedding_profile_id = Column(
        Integer, ForeignKey("embedding_profiles.id", ondelete="SET NULL"), nullable=True
    )

    updated_by = relationship("User")
    active_profile = relationship("AIProfile", foreign_keys=[active_profile_id])
    active_embedding_profile = relationship(
        "EmbeddingProfile", foreign_keys=[active_embedding_profile_id]
    )


class AIProfile(Base):
    """Server-side inference profile; secrets never leave the API service."""

    __tablename__ = "ai_profiles"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    kind = Column(String(32), nullable=False)  # local | remote | cloud
    provider = Column(String(32), nullable=False)
    protocol = Column(String(32), nullable=False)
    llm_model = Column(String, nullable=False)
    llm_base_url = Column(String, nullable=True)
    llm_path = Column(String, nullable=True)
    llm_api_key = Column(EncryptedString, nullable=True)
    embedding_provider = Column(String(32), nullable=False, server_default="ollama")
    embedding_model = Column(String, nullable=False, server_default="bge-m3")
    embedding_base_url = Column(String, nullable=True)
    embedding_path = Column(String, nullable=True)
    embedding_api_key = Column(EncryptedString, nullable=True)
    embedding_dimension = Column(Integer, nullable=False, server_default="1024")
    embedding_context_length = Column(Integer, nullable=False, server_default="8192")
    llm_context_length = Column(Integer, nullable=False, server_default="8192")
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EmbeddingProfile(Base):
    """Independent embedding endpoint used by imports and retrieval."""

    __tablename__ = "embedding_profiles"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    provider = Column(String(32), nullable=False, server_default="ollama")
    model = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    path = Column(String, nullable=False, server_default="/api/embed")
    api_key = Column(EncryptedString, nullable=True)
    dimension = Column(Integer, nullable=False, server_default="1024")
    context_length = Column(Integer, nullable=False, server_default="8192")
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatFeedbackDiagnosticCase(Base):
    """Minimaler, lokaler Support-Fall aus einem bewusst erfassten Downvote."""

    __tablename__ = "chat_feedback_diagnostic_cases"
    id = Column(Integer, primary_key=True, index=True)
    chat_message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True
    )
    question = Column(EncryptedString, nullable=True)
    answer = Column(EncryptedString, nullable=False)
    sources_json = Column(JSON, nullable=True)
    model = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("ChatMessage")
    project = relationship("Project")
    source = relationship("KnowledgeSource")


class MCPToolAuditLog(Base):
    """Data-minimal audit entry for one executed MCP tool call.

    Tool results are intentionally excluded because they may contain large or
    external content and remain traceable through the chat turn itself.
    """

    __tablename__ = "mcp_tool_audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chat_session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chat_message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    server_name = Column(String(120), nullable=False)
    tool_name = Column(String(200), nullable=False)
    arguments_json = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False)  # "success" or "error"
    error_message = Column(String(1000), nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    trace_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user = relationship("User")
    chat_session = relationship("ChatSession")
    chat_message = relationship("ChatMessage")
    project = relationship("Project")
    knowledge_source = relationship("KnowledgeSource")


class CodeEntity(Base):
    """
    Ein geparstes COBOL-Objekt. Die Hierarchie Programm→Section→Paragraph bzw.
    Programm→DataItem wird über parent_id abgebildet (F-030).
    """

    __tablename__ = "code_entities"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_path = Column(String, index=True)
    name = Column(String, index=True)
    # 'program'|'copybook'|'section'|'paragraph'|'data_item'|'file_fd'|'sql_table'|'sql_block'|'entry'
    # v2 zusätzlich: 'jcl_job'|'jcl_step'
    type = Column(String, index=True)
    parent_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Stabiler Schlüssel für Deep-Links: 'XAAOA.MAIN-SECTION.INIT-PARA'
    qualified_name = Column(String, nullable=True)
    # O-150: dieselbe Quelle kann mehrere bestätigte Buildvarianten tragen;
    # ihre gleichnamigen Artefakte dürfen sich nicht gegenseitig überschreiben.
    variant_key = Column(String(64), nullable=False, server_default="default", index=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    # PIC-Klausel, Level, OCCURS/REDEFINES, SQL-Statement-Typ, Format (fixed/free)
    meta_json = Column(JSON, nullable=True)
    # Inkrementalität: unveränderte Datei → Entities/Kanten nicht neu schreiben
    content_hash = Column(String(64), nullable=True)
    # O-180: incremented when the entity content changes. The link builder uses
    # this together with the entity hash to keep link decisions reproducible.
    link_revision = Column(Integer, nullable=False, server_default="0")
    # Model used for the persisted entity-side retrieval embedding during the
    # last link run. Entities do not store a vector yet, but the model belongs
    # to the entity-side link state and must be auditable.
    embedding_model = Column(String, nullable=True)

    children = relationship(
        "CodeEntity",
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "variant_key",
            "file_path",
            "qualified_name",
            name="uq_code_entities_source_variant_file_qname",
        ),
        Index("ix_code_entities_source_type", "source_id", "type"),
    )


EDGE_DIRECTION_DIRECTED = "directed"
EDGE_DIRECTION_UNDIRECTED = "undirected"
EDGE_DIRECTION_BIDIRECTIONAL = "bidirectional"
VALID_EDGE_DIRECTIONS = frozenset(
    {EDGE_DIRECTION_DIRECTED, EDGE_DIRECTION_UNDIRECTED, EDGE_DIRECTION_BIDIRECTIONAL}
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
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    src_entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dst_name = Column(String, nullable=False, index=True)
    # v1: CALL | PERFORM | GOTO | COPY | DEFINES | USES | READS | WRITES — v2: EXECUTES
    type = Column(String, nullable=False, index=True)
    # 'resolved' | 'unresolved' | 'dynamic'
    resolution = Column(String, nullable=False, server_default="unresolved")
    # Programmlokale Kantenarten (PERFORM/GO TO/USES) dürfen NUR innerhalb ihres
    # Programms aufgelöst werden: Paragraphennamen wie INIT-PARA existieren in
    # hunderten Programmen. Der Nachlauf-Pass filtert darüber, sonst entsteht ein
    # falsch verdrahteter Call-Graph (siehe docs/ENTSCHEIDUNGEN.md, E-1).
    scope_entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    src_start_line = Column(Integer, nullable=False, server_default="0")
    src_end_line = Column(Integer, nullable=False, server_default="0")
    variant_key = Column(String(64), nullable=False, server_default="default", index=True)
    meta_json = Column(JSON, nullable=True)  # z.B. {"thru": "END-PARA"}, {"replacing": [...]}

    src_entity = relationship("CodeEntity", foreign_keys=[src_entity_id])
    dst_entity = relationship("CodeEntity", foreign_keys=[dst_entity_id])

    @property
    def direction(self) -> str:
        """Deterministische Standard-Richtung für Code-Kanten (O-264).
        Code-Kanten (CALL, EXTENDS, IMPLEMENTS, READS, WRITES etc.) sind
        immer gerichtet von src_entity nach dst_entity.
        """
        return EDGE_DIRECTION_DIRECTED

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
    link_type = Column(String, default="semantic")  # "semantic" | "manual"
    status = Column(String, default="pending", index=True)  # "pending" | "approved" | "rejected"
    context = Column(Text, nullable=True)  # LLM-Begründung oder manuelle Notiz
    created_by = Column(String, default="auto")  # "auto" | "user"
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # O-180: snapshot of both link endpoints at recommendation time. Approved
    # and rejected decisions can therefore survive unrelated delta-syncs while
    # pending recommendations can be invalidated precisely.
    entity_content_hash = Column(String(64), nullable=True)
    chunk_content_hash = Column(String(64), nullable=True)
    embedding_model = Column(String, nullable=True)
    entity_link_revision = Column(Integer, nullable=True)
    chunk_link_revision = Column(Integer, nullable=True)

    project = relationship("Project", backref="entity_doc_links")
    entity = relationship("CodeEntity", backref="doc_links")
    chunk = relationship("DocumentChunk", backref="entity_links")

    @property
    def direction(self) -> str:
        """Deterministische Standard-Richtung für Dokumentationskanten (O-264).
        EntityDocLink dokumentiert eine Code-Entity durch einen Dokumenten-Chunk.
        """
        return EDGE_DIRECTION_DIRECTED


class LinkBuilderDirtyItem(Base):
    """Coalesced work item for incremental entity/document link building."""

    __tablename__ = "link_builder_dirty_items"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    chunk_id = Column(
        Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reason = Column(String(40), nullable=False, server_default="content_changed")
    status = Column(String(20), nullable=False, server_default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project")
    entity = relationship("CodeEntity")
    chunk = relationship("DocumentChunk")

    __table_args__ = (
        Index(
            "ix_link_builder_dirty_pending_scope",
            "project_id",
            "status",
            "entity_id",
            "chunk_id",
        ),
    )


class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    color = Column(String(20), default="indigo")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    nodes = relationship(
        "TopicNode",
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="TopicNode.node_type",
    )


class TopicNode(Base):
    __tablename__ = "topic_nodes"
    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    node_type = Column(
        String(30), nullable=False
    )  # 'project' | 'repository' | 'entity' | 'document' | 'knowledge_source'
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
    source_id = Column(
        Integer, ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path = Column(String, nullable=False)
    content_hash = Column(String(32), nullable=False)
    # O-122: SHA-256 über Git-Revision, effektives Buildprofil, Parser-/
    # Grammatikstand und Copybook-Bibliotheken. Anders als content_hash löst
    # er daher auch ohne Textänderung gezielt einen Reparse aus.
    analysis_fingerprint = Column(String(64), nullable=True)
    # O-120: 'complete' | 'partial' | 'text_fallback' | 'skipped' | 'error'
    # (core.model.AnalysisStatus plus 'error' für DB-seitige Persistenzfehler,
    # siehe connectors/git.py::_save_document_chunks). Vor O-120 nur
    # 'ok'/'fallback_text'/'error', abgeleitet allein aus ParseResult.errors —
    # ignorierte die O-119-Diagnosen und unterschied nicht zwischen "Struktur
    # mit Einschränkungen" (jetzt 'partial') und "gar keine Struktur, nur
    # Volltext" (jetzt 'text_fallback', F-029). 'skipped' ist neu: eine Datei,
    # die nie beim Parser ankam (Binärformat/Größenlimit/kein UTF-8, siehe
    # GitConnector._record_skip) — vorher komplett unsichtbar (nur Sync-Log).
    parse_status = Column(String, nullable=True)
    parse_error = Column(Text, nullable=True)
    # O-242: Klassifikation und tatsächlich verwendetes Encoding für den
    # nachvollziehbaren Importbericht. Das Sprachlabel verspricht keinen
    # vorhandenen Strukturparser.
    language = Column(String(50), nullable=True)
    encoding = Column(String(50), nullable=True)
    # O-137: {pfad: content_hash} der beim letzten erfolgreichen Parsen
    # eindeutig aufgelösten, (transitiv) verwendeten Copybooks - ermöglicht
    # connectors/git.py eine präzise statt konservative (voller Bestand)
    # Fingerprint-Eingrenzung. NULL = noch kein Eintrag oder Nicht-COBOL,
    # dann bleibt es beim konservativen Verhalten.
    copybook_dependencies = Column(JSON, nullable=True)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("source_id", "file_path", name="uq_source_scan_source_path"),
    )

    # passive_deletes=True: siehe Begruendung bei KnowledgeSource.project oben.
    # Ohne dieses Flag versucht SQLAlchemy beim Loeschen einer KnowledgeSource,
    # source_id hier per UPDATE auf NULL zu setzen statt die DB-CASCADE greifen
    # zu lassen — schlaegt fehl, weil source_id NOT NULL ist (IntegrityError beim
    # Loeschen jeder Quelle mit Scan-Journal, u.a. Git).
    knowledge_source = relationship(
        "KnowledgeSource", backref=backref("scan_files", passive_deletes=True)
    )


class KnowledgeLink(Base):
    __tablename__ = "knowledge_links"
    id = Column(Integer, primary_key=True, index=True)

    # Source A (can be Code-Entity OR DocumentChunk)
    source_a_type = Column(String(20), nullable=False)  # 'entity' | 'document'
    source_a_entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True
    )
    source_a_chunk_id = Column(
        Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True
    )
    source_a_title = Column(Text, nullable=False)
    source_a_url = Column(Text, nullable=True)
    source_a_source_type = Column(String(50), nullable=True)  # 'Git', 'Confluence', 'Jira', 'Local'

    # Source B (can be Code-Entity OR DocumentChunk)
    source_b_type = Column(String(20), nullable=False)  # 'entity' | 'document'
    source_b_entity_id = Column(
        Integer, ForeignKey("code_entities.id", ondelete="CASCADE"), nullable=True
    )
    source_b_chunk_id = Column(
        Integer, ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True
    )
    source_b_title = Column(Text, nullable=False)
    source_b_url = Column(Text, nullable=True)
    source_b_source_type = Column(String(50), nullable=True)

    # Link Metadata
    score = Column(Float, nullable=True)
    link_type = Column(String(20), default="semantic")  # 'semantic', 'keyword', 'chat', 'manual'
    # O-264: Directionality of the relationship ('undirected' | 'directed' | 'bidirectional')
    # 'undirected': mutual semantic cross-reference without inherent flow.
    # 'directed': directed connection from source_a to source_b.
    # 'bidirectional': explicit two-way relation.
    direction = Column(
        String(20), default="undirected", nullable=False, server_default="undirected"
    )
    status = Column(String(20), default="pending", index=True)  # 'pending', 'approved', 'rejected'
    context = Column(Text, nullable=True)  # Why this link? (AI explanation)
    created_by = Column(String(50), default="auto")  # 'auto', 'user', 'chat'
    chat_session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_a_entity = relationship("CodeEntity", foreign_keys=[source_a_entity_id])
    source_a_chunk = relationship("DocumentChunk", foreign_keys=[source_a_chunk_id])
    source_b_entity = relationship("CodeEntity", foreign_keys=[source_b_entity_id])
    source_b_chunk = relationship("DocumentChunk", foreign_keys=[source_b_chunk_id])
    chat_session = relationship("ChatSession")

    __table_args__ = (
        CheckConstraint(
            "direction IN ('directed', 'undirected', 'bidirectional')",
            name="ck_knowledge_links_direction",
        ),
    )


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
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(
        String, default="pending", nullable=False
    )  # pending, running, completed, failed
    celery_task_id = Column(String(255), nullable=True)
    progress_message = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    links_created = Column(Integer, nullable=False, default=0)
    # Embedding space selected for this run; retained for audit/reproducibility.
    embedding_model = Column(String, nullable=True)
    # O-177: exact project/source scope used by a cross-source run.
    scope_json = Column(JSON, nullable=True)
    # Audit trail for privileged/global runs (O-178).
    triggered_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )


class DiagnosticsRun(Base):
    """
    One invocation of the diagnostics-bundle Celery task (triggered via the
    Settings > Logs "Generate Diagnostics Bundle" button). Same
    pending/running/completed/failed shape as LinkBuilderRun — a crash here must
    be as visible as the failure it's meant to help diagnose.
    """

    __tablename__ = "diagnostics_runs"
    id = Column(Integer, primary_key=True, index=True)
    triggered_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(
        String, default="pending", nullable=False
    )  # pending, running, completed, failed
    celery_task_id = Column(String(255), nullable=True)
    progress_message = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    bundle_path = Column(String, nullable=True)  # tar.gz path under the shared ./repos mount


class JobCenterDismissal(Base):
    """Admin dismissal of a completed entry without deleting its domain record."""

    __tablename__ = "job_center_dismissals"
    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)
    job_id = Column(Integer, nullable=False)
    dismissed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("kind", "job_id", name="uq_job_center_dismissals_kind_job"),)
