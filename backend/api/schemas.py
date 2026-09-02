"""
backend/api/schemas.py
=======================
Pydantic-Request-Schemas für alle API-Endpoints.

Alle Eingabe-Validierungsmodelle sind hier zentralisiert statt verteilt über
die Router-Dateien. Router-Module importieren nur was sie brauchen.
"""

from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel


class RepoCreate(BaseModel):
    name: str
    url: str
    branch: str = "main"
    username: Optional[str] = None
    token: Optional[str] = None

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    team_id: Optional[int] = None
    color: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_archived: Optional[bool] = None
    color: Optional[str] = None
    expose_code_analysis_globally: Optional[bool] = None

class ProjectMembershipCreate(BaseModel):
    user_id: int
    role: str = "member"

class ProjectMembershipRoleUpdate(BaseModel):
    role: str

class ProjectAccessRequestUpdate(BaseModel):
    status: str  # "approved" | "rejected"

class ProjectCompleteRequest(BaseModel):
    promote_source_ids: List[int] = []


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    project_id: Optional[int] = None
    source_id: Optional[int] = None
    branch: str = "main"
    pinned_file: Optional[str] = None
    pinned_line: Optional[int] = None
    pinned_context: Optional[str] = None
    pinned_label: Optional[str] = None
    pinned_source_id: Optional[int] = None
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None
    llm_provider: Optional[str] = "ollama"
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    metadata: Optional[dict] = None
    retry_of_message_id: Optional[int] = None  # regenerate: replaces this assistant message instead of appending a new turn


class ChatSnapshotUpdate(BaseModel):
    """Content-/Navigationsstate des Workspace (Panels, offene Dateien/Docs/Entities) — s. buildWorkspaceSnapshot im Frontend."""
    snapshot: dict


class ChatMessageFeedbackUpdate(BaseModel):
    feedback: Optional[str] = None  # 'up' | 'down' | null (null clears it)


class ConnectorTestRequest(BaseModel):
    """Verbindungstest für Git- und Wissensquellen-Connectoren."""
    type: str  # 'github' | 'bitbucket' | 'gitlab' | 'confluence' | 'jira'
    username: Optional[str] = None
    token: str
    url: Optional[str] = None


class ConnectorReposRequest(BaseModel):
    type: str
    username: Optional[str] = None
    token: str
    url: Optional[str] = None  # Bitbucket Server/Data Center base URL


class ConnectorBranchesRequest(BaseModel):
    type: str
    username: Optional[str] = None
    token: Optional[str] = None
    repo_name: str
    url: Optional[str] = None  # Bitbucket Server/Data Center base URL


class KnowledgeSourceCreate(BaseModel):
    name: str
    type: str  # "Git" | "Confluence" | "Jira" | "WebDAV" | "FolderWatch" | "Local"
    url: Optional[str] = None
    username: Optional[str] = None
    token: Optional[str] = None
    project_id: Optional[int] = None
    spaces: Union[List[str], Dict[str, Any]] = []
    team_id: Optional[int] = None
    sync_interval_minutes: Optional[int] = None  # Auto-Sync-Intervall; None → Server-Default (60), 0 → nur manuell
    context_note: Optional[str] = None  # Fachwissen-Notiz für den System-Prompt, siehe KnowledgeSource.context_note


class FolderWatchCreate(BaseModel):
    name: str
    folder_path: str  # Absoluter Pfad innerhalb des Containers (z. B. /watched)
    project_id: Optional[int] = None
    team_id: Optional[int] = None
    sync_interval_minutes: Optional[int] = None


class GitSourceCreate(BaseModel):
    name: str
    url: str
    branch: Optional[str] = None
    username: Optional[str] = None
    token: Optional[str] = None
    project_id: Optional[int] = None
    team_id: Optional[int] = None
    sparse_paths: Optional[List[str]] = None
    sync_interval_minutes: Optional[int] = None


class KnowledgeSourceUpdate(BaseModel):
    # Beide Felder optional: der Endpunkt aktualisiert per model_dump(exclude_unset=True)
    # nur, was der Client tatsächlich mitschickt — sonst würde ein Speichern der
    # Kontext-Notiz allein das Sync-Intervall unbeabsichtigt auf den Default zurücksetzen.
    sync_interval_minutes: Optional[int] = None  # 0 = nur manuell, sonst Auto-Sync-Intervall in Minuten
    context_note: Optional[str] = None  # Fachwissen-Notiz für den System-Prompt, siehe KnowledgeSource.context_note


class LinkStatusUpdate(BaseModel):
    status: Optional[str] = None    # "approved" | "rejected"
    context: Optional[str] = None   # Beschreibung, wie die Verknüpfung inhaltlich zusammenhängt (F-032-Erweiterung)


class LlmReviewRequest(BaseModel):
    """Body für POST .../llm-review — welches LLM-Profil (Header-Dropdown im
    Link Manager) den Einzel-Link neu bewerten soll. Gleiche vier Felder wie
    ChatRequest.llm_*, hier separat statt geteilt, da der Rest von ChatRequest
    (message, session_id, ...) hier nicht zutrifft. Default "ollama" hält
    bestehende Aufrufer ohne Body funktionsfähig (Backend bleibt zustandslos —
    Regel 3 in CLAUDE.md: der API-Key kommt im Request, nie aus Serverstate)."""
    llm_provider: Optional[str] = "ollama"
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None


class ManualLinkCreate(BaseModel):
    entity_id: int
    doc_title: str
    doc_url: Optional[str] = None
    source_type: Optional[str] = None
    context: Optional[str] = None


class ModelUpdateRequest(BaseModel):
    llm: str


class KnowledgeLinkCreate(BaseModel):
    source_a_type: str  # 'entity' | 'document'
    source_a_entity_id: Optional[int] = None
    source_a_chunk_id: Optional[int] = None
    source_a_title: str
    source_a_url: Optional[str] = None
    source_a_source_type: Optional[str] = None
    
    source_b_type: str  # 'entity' | 'document'
    source_b_entity_id: Optional[int] = None
    source_b_chunk_id: Optional[int] = None
    source_b_title: str
    source_b_url: Optional[str] = None
    source_b_source_type: Optional[str] = None
    
    link_type: Optional[str] = "manual"
    status: Optional[str] = "approved"
    context: Optional[str] = None
    chat_session_id: Optional[int] = None


class KnowledgeLinkUpdate(BaseModel):
    status: Optional[str] = None    # "approved" | "rejected" | "pending"
    context: Optional[str] = None   # Beschreibung, wie die Verknüpfung inhaltlich zusammenhängt


class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "indigo"


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class TopicNodeAttach(BaseModel):
    node_type: str  # 'project' | 'repository' | 'entity' | 'document' | 'knowledge_source'
    node_id: int
    node_label: str
    node_url: Optional[str] = None
    node_meta: Optional[dict] = None
