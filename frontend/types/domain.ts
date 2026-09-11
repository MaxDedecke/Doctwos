import type { ChatPinnedFocus, ChatTurnFocus } from '@/lib/chatFocus';
import type { PanelSelection } from '@/lib/panelHistory';

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
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
}
export type AgentStep =
  | { type: 'thought'; content: string }
  | { type: 'tool_call'; name: string; arguments: unknown; id?: string }
  | { type: 'tool_result'; name: string; result: string; id?: string; truncated?: boolean };
export interface ChatMetadata {
  focus?: ChatTurnFocus;
  project?: ChatTurnFocus['project'];
  source?: ChatTurnFocus['source'];
  pinned?: (Partial<ChatPinnedFocus> & { source_id?: number | string | null }) | null;
  refs?: ChatReference[];
  agent_steps?: AgentStep[];
  model?: string;
  provider?: string;
  [key: string]: unknown;
}
export interface ChatSource {
  file: string;
  source_id?: number | string | null;
  /** Internal exact reference used for feedback-to-link mapping; never rendered. */
  chunk_id?: number | null;
  lines?: Array<number | null>;
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
  branch: string;
  temperature: number;
  system_prompt: string;
  llm_provider: string;
  llm_model?: string;
  llm_api_key?: string;
  llm_base_url?: string;
  metadata: ChatMetadata;
  retry_of_message_id?: number;
}
export type ChatStreamEvent =
  | { type: 'session'; session_id: number; session_uuid?: string; session_title?: string }
  | { type: 'sources'; sources: ChatSource[] }
  | { type: 'content_chunk'; content: string }
  | Extract<AgentStep, { type: 'tool_call' | 'tool_result' }>
  | { type: 'turn_completed'; has_tool_calls: boolean }
  | { type: 'answer'; content: string; agent_steps?: AgentStep[] }
  | { type: 'message_saved'; message_id: number }
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
  dst_name: string;
  entity: CodeEntity | null;
  document?: { title: string; file_path: string | null; source_id: number | null; url: string | null; source_type: string; score: number | null; link_type: string };
  start_line: number | null;
  end_line: number | null;
}
export interface User {
  id: number;
  username: string;
  name?: string | null;
  email?: string | null;
  role?: string;
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
