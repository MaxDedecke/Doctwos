import type { ChatPinnedFocus, ChatTurnFocus } from '@/lib/chatFocus';
import type { PanelSelection } from '@/lib/panelHistory';
export type { CallFlowData, CallFlowNode, CallFlowEdge } from '@/lib/callFlow';

/** Project list and session summaries share identity; repository fields exist only on full projects. */
export interface Project {
  id: number;
  name: string;
  description?: string | null;
  color?: string | null;
  team_id?: number | null;
  creator_id?: number | null;
  repo_id?: number | null;
  url?: string | null;
  branch?: string | null;
  status?: string | null;
  is_archived?: boolean;
  is_admin?: boolean;
  expose_code_analysis_globally?: boolean;
  progress?: number;
  progress_message?: string | null;
}
export interface KnowledgeSource {
  id: number | string;
  name: string;
  type?: string;
  project_id?: number | null;
  team_id?: number | null;
  url?: string | null;
  repoId?: string;
  repo_id?: number | string | null;
  branch?: string;
  spaces?: string[] | { filename?: string; branch?: string; [key: string]: unknown } | null;
  sync_status?: string | null;
  sync_log?: string | null;
  last_error?: string | null;
  sync_interval_minutes?: number;
  progress?: number;
  progress_message?: string | null;
  context_note?: string | null;
  embedding_model?: string | null;
  last_synced_at?: string | null;
}
/** Navigation projections may omit the database ID; unresolved entities can have no source line. */
export interface CodeEntity {
  id?: number;
  name: string;
  type?: string;
  file_path: string;
  start_line: number | null;
  end_line?: number | null;
  source_id?: number | string | null;
  project_id?: number | null;
  parent_id?: number | null;
  qualified_name?: string | null;
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
  meta?: Record<string, unknown>;
}
export interface WorkspaceDocument {
  id: number | string;
  name: string;
  url?: string | null;
  isWebOrigin?: boolean;
  type?: string;
  chunkId?: number;
  excerpt?: string;
  page?: number | null;
  section?: string | null;
  startLine?: number | null;
  endLine?: number | null;
  urlAnchor?: string | null;
  sourceRevision?: string | null;
  locatorPrecision?: string | null;
  indexedExcerpt?: boolean;
}
export interface FocusObject {
  kind?: string;
  name: string;
  type?: string;
  material?: string;
  volume?: number;
  fireRating?: string;
}
export type PanelTab = 'code' | 'doc' | 'weborigin' | 'graph';
export interface FileNavEntry { file: string | null; doc: WorkspaceDocument | null; tab: PanelTab }
/** Fields are optional because stored sessions can predate individual layout features. */
export interface WorkspaceSnapshot {
  panelConfigs?: string[];
  panelFrozen?: boolean[];
  panelSelections?: PanelSelection[];
  panelFocusObject?: Array<FocusObject | null>;
  fileNavStack?: FileNavEntry[];
  pinnedCode?: ChatPinnedFocus | null;
  activeRightTab?: PanelTab;
  selectedProjectId?: number | null;
  selectedSourceId?: number | string | null;
  splitPercent?: number;
  gridColumnPercent?: number;
  gridRowPercent?: number;
  threeColLeftPercent?: number;
  threeColRightPercent?: number;
}
export interface ChatReference {
  file: string;
  line: number;
  end_line?: number | null;
  label?: string | null;
  source_id?: number | string | null;
  entity_id?: number | null;
  entity_type?: string | null;
  qualified_name?: string | null;
  breadcrumb?: string | null;
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
}
export type AgentViewActionStatus = 'requested' | 'opened' | 'updated' | 'manual' | 'declined' | 'no_space' | 'rejected' | 'stale_context';
interface AgentViewActionBase {
  type: 'view_action';
  action_id: string;
  session_id: number;
  turn_id: number;
  project_id: number | null;
  tool_call_id: string;
  status: AgentViewActionStatus;
}
export interface AgentCallGraphViewAction extends AgentViewActionBase {
  view: 'callgraph';
  target: { entity_id: number; focus_entity_id?: number; highlighted_edge_id?: number };
}
export interface AgentGraphViewAction extends AgentViewActionBase {
  view: 'graph';
  target: {
    focus_id: string;
    focus_label: string;
    direction: 'incoming' | 'outgoing' | 'both';
    hops: 1;
    limit: number;
    relationships: Array<'code_dependency' | 'documented' | 'manual'>;
  };
}
export interface AgentSearchViewAction extends AgentViewActionBase {
  view: 'search';
  target: {
    query: string;
    types: Array<'entity' | 'document'>;
    project_id: number;
    source_id: number | null;
    limit: 10;
  };
}
export interface AgentCodeViewAction extends AgentViewActionBase {
  view: 'code';
  target: { file_path: string; start_line: number; end_line: number };
}
export interface CodeWalkthroughStep {
  kind?: 'code';
  file_path: string;
  start_line: number;
  end_line: number;
  explanation: string;
}
export interface CallGraphWalkthroughStep {
  kind: 'callgraph';
  trace_tool_call_id: string;
  edge_id: number;
  source_entity_id: number;
  target_entity_id: number;
  source_name: string;
  target_name: string;
  file_path: string;
  start_line?: number | null;
  end_line?: number | null;
  explanation: string;
}
export interface DocumentWalkthroughStep {
  kind: 'document';
  chunk_id: number;
  source_id: number;
  file_path: string;
  start_line?: number | null;
  end_line?: number | null;
  page?: number | null;
  section?: string | null;
  source_type?: string | null;
  url?: string | null;
  excerpt: string;
  explanation: string;
}
export interface AgentWalkthroughViewAction extends AgentViewActionBase {
  view: 'walkthrough';
  target: { title: string; steps: Array<CodeWalkthroughStep | CallGraphWalkthroughStep | DocumentWalkthroughStep> };
}
export interface AgentDocumentViewAction extends AgentViewActionBase {
  view: 'document';
  target: DocumentWalkthroughStep;
}
export type AgentViewAction = AgentCallGraphViewAction | AgentGraphViewAction | AgentSearchViewAction | AgentCodeViewAction | AgentWalkthroughViewAction | AgentDocumentViewAction;
export type AgentStep =
  | { type: 'thought'; content: string }
  | { type: 'tool_call'; name: string; arguments: unknown; id?: string }
  | { type: 'tool_result'; name: string; result: string; id?: string; truncated?: boolean }
  | AgentViewAction;
export interface ChatMetadata {
  focus?: ChatTurnFocus;
  project?: ChatTurnFocus['project'];
  source?: ChatTurnFocus['source'];
  pinned?: (Partial<ChatPinnedFocus> & {
    source_id?: number | string | null;
    entity_id?: number | null;
    entity_type?: string | null;
    qualified_name?: string | null;
  }) | null;
  refs?: ChatReference[];
  agent_steps?: AgentStep[];
  telemetry?: ChatTelemetry;
  model?: string;
  provider?: string;
  [key: string]: unknown;
}

export interface ChatTelemetryMetrics {
  response_time_ms: number | null;
  first_token_ms: number | null;
  tool_count: number;
  retrieval_wait_ms: number | null;
  first_tool_call_ms: number | null;
  model_end_ms: number | null;
}

export interface ChatTelemetry {
  events: Array<{ event: string; monotonic_ms: number }>;
  metrics: ChatTelemetryMetrics;
}
export interface ChatSource {
  file: string;
  source_id?: number | string | null;
  /** Internal exact reference used for feedback-to-link mapping; never rendered. */
  chunk_id?: number | null;
  lines?: Array<number | null>;
  provenance?: Record<string, unknown>;
}
export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sources?: ChatSource[];
  metadata?: ChatMetadata;
  feedback?: 'up' | 'down' | null;
}
export interface StoredChatMessage extends Omit<ChatMessage, 'sources' | 'metadata'> {
  sources_json?: ChatSource[] | null;
  metadata_json?: ChatMetadata | null;
}
/** Admin-only O-086 review projection; intentionally contains only downvoted turns. */
export interface ChatFeedbackReview {
  message_id: number;
  // Bewusst kein session_id: der Sitzungsinhaber soll aus dieser Auswertung
  // nicht ermittelbar sein (O-086-Erweiterung). session_label ist nur eine
  // pro Abruf neu vergebene, fortlaufende Kennung zum Gruppieren.
  session_label: number;
  question: string | null;
  answer: string;
  sources_json: ChatSource[];
  metadata_json: ChatMetadata;
  created_at: string | null;
}
export interface ChatFeedbackDiagnosticSettings {
  collection_enabled: boolean;
  support_export_enabled: boolean;
  retention_days: number;
  updated_at: string | null;
}
export interface ChatSession {
  id: number;
  title: string;
  uuid?: string | null;
  project_id?: number | string | null;
  source_id?: number | string | null;
  project?: Project | null;
  source?: KnowledgeSource | null;
  snapshot_json?: WorkspaceSnapshot | null;
  created_at?: string | null;
  is_public?: boolean;
}
export interface ChatRequest {
  message: string;
  session_id: number | null;
  project_id: number | string | null;
  source_id: number | string | null;
  pinned_file: string | null;
  pinned_line: number | null;
  pinned_end_line: number | null;
  pinned_context: string | null;
  pinned_label: string | null;
  pinned_source_id: number | string | null;
  pinned_entity_id: number | null;
  branch: string;
  temperature: number;
  system_prompt: string;
  llm_provider: string;
  llm_model?: string;
  llm_api_key?: string;
  llm_base_url?: string;
  llm_profile_id?: number;
  embedding_model?: string;
  metadata: ChatMetadata;
  retry_of_message_id?: number;
}
export type ChatStreamEvent =
  | { type: 'session'; session_id: number; session_uuid?: string; session_title?: string }
  | { type: 'sources'; sources: ChatSource[] }
  | { type: 'content_chunk'; content: string }
  | Extract<AgentStep, { type: 'tool_call' | 'tool_result' | 'view_action' }>
  | { type: 'turn_completed'; has_tool_calls: boolean }
  | { type: 'answer'; content: string; agent_steps?: AgentStep[] }
  | { type: 'message_saved'; message_id: number }
  | { type: 'telemetry'; event: string; monotonic_ms?: number; metrics?: ChatTelemetryMetrics }
  | { type: 'error'; error: string };
export interface ProjectStats {
  total_files: number;
  total_lines: number;
  languages: Array<{ name: string; lines: number; percentage: number }>;
}
export interface FileReference {
  id?: number | string;
  node_type?: string;
  name?: string;
  title?: string;
  file_path: string;
  line?: number | null;
  source_id?: number | string | null;
  source?: string;
  url?: string | null;
  preview?: string;
}
export interface EntityNeighbor {
  edge_id: number | string;
  type: string;
  direction: string;
  resolution: string | null;
  variant_key?: string;
  meta?: Record<string, unknown>;
  dst_name: string;
  entity: CodeEntity | null;
  reference?: {
    entity_id: number | null;
    name?: string | null;
    file_path: string | null;
    source_id: number | string | null;
    start_line: number | null;
    end_line?: number | null;
  } | null;
  document?: {
    title: string;
    file_path: string | null;
    source_id: number | null;
    chunk_id?: number | null;
    start_line?: number | null;
    end_line?: number | null;
    page?: number | null;
    section?: string | null;
    url: string | null;
    url_anchor?: string | null;
    source_revision?: string | null;
    locator_precision?: string | null;
    excerpt?: string | null;
    source_type: string;
    score: number | null;
    link_type: string;
  };
  start_line: number | null;
  end_line: number | null;
}
export interface User {
  id: number;
  username: string;
  name?: string | null;
  email?: string | null;
  role?: string;
  auth_provider?: 'oidc' | 'local';
  is_admin?: boolean;
  is_active?: boolean;
  must_change_password?: boolean;
  teams?: Team[];
}
export interface Team { id: number; name: string }
export interface SearchResult {
  node_type: string;
  node_id: number;
  node_label: string;
  node_url: string | null;
  node_meta: { project_id?: number | null; source_id?: number | null; file_path?: string; start_line?: number; type?: string; [key: string]: unknown };
}
export interface ProjectMember { id: number; user_id: number; user_name: string | null; user_email?: string | null; role: 'admin' | 'member' }
export interface ProjectAccessRequest { id: number; user_id: number; user_name: string | null; user_email?: string | null; status: string; created_at?: string }
export interface DiscoverableProject extends Project { team_name?: string; member_count?: number; request_status?: string | null }
export interface DiagnosticsRun { id: number; status: string; error?: string | null }
export interface McpAuditEntry { id: number; status: string; created_at?: string; tool_name: string; server_name: string; user_name?: string; duration_ms?: number; project_name?: string; trace_id?: string; arguments?: unknown; error_message?: string }

export interface SystemConfigResponse {
  sso: {
    enabled: boolean;
    issuer: string | null;
    client_id: string | null;
    client_secret_configured: boolean;
    redirect_uri: string | null;
    default_team: string | null;
    default_team_exists: boolean | null;
    admin_roles: string[];
    team_mapping: Record<string, string>;
    roles_claim: string;
    groups_claim: string;
  };
  system: {
    version: string;
    api_url: string;
    frontend_url: string;
    log_level: string;
    mcp_audit_retention_days: number;
    watched_folder: string | null;
    llm_model: string;
    embed_model: string;
    context_window: number;
  };
  secrets: {
    master_encryption_key_configured: boolean;
    session_secret_key_configured: boolean;
  };
  existing_teams: string[];
}

export interface OidcConnectionTestResult {
  success: boolean;
  duration_ms?: number;
  issuer?: string;
  authorization_endpoint?: string;
  token_endpoint?: string;
  userinfo_endpoint?: string;
  jwks_uri?: string;
  end_session_endpoint?: string;
  error?: string;
}

export interface OidcMappingSimulationResult {
  computed_role: 'superuser' | 'user';
  extracted_items: string[];
  teams: Array<{ name: string; exists: boolean }>;
}
