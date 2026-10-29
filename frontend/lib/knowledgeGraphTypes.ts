export interface GraphNode {
  id: string;
  type: 'insight' | 'entity' | 'code_file' | 'document' | 'copybook' | 'external' | 'group';
  label: string;
  content?: string;
  status?: string;
  evidence?: Array<Record<string, unknown>>;
  entity_type?: string;
  language?: string;
  analysis_status?: 'partial' | 'text_fallback' | 'skipped' | 'error';
  analysis_reasons?: string[];
  file_path?: string;
  start_line?: number;
  source_type?: string;
  url?: string;
  project_id?: number;
  unresolved?: boolean;
  source_id?: number | string | null;
  entity_ids?: number[];
  resource_type?: string;
  resource_id?: string | number | null;
  /** Total connections on the server; more than the loaded edges means some are not shown. */
  degree?: number;
  /** Group nodes (type 'group'): files grouped by coupling or a topic, expandable in place. */
  group_key?: string;
  group_kind?: 'community' | 'topic';
  file_count?: number;
  doc_count?: number;
  topic_color?: string | null;
  path_prefix?: string;
  central_file?: string;
  /** Set on everything shown because its group is expanded; collapsing returns to the group. */
  group_parent?: string | null;
  group_parent_label?: string | null;
  /** A file shown on its own (neighborhood, in-place expansion) names the group it belongs to. */
  member_group?: string | null;
  member_group_label?: string | null;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  link_type: string;
  /** Broad graph relationship family, e.g. `documented` for EntityDocLink. */
  relation_type?: string;
  /** O-264/O-265: Directionality of the relationship ('directed' | 'undirected' | 'bidirectional') */
  direction?: 'directed' | 'undirected' | 'bidirectional';
  score: number | null;
  context: string | null;
  /** Optional code-edge fields; relationship types remain open strings. */
  type?: string;
  resolution?: string | null;
  meta?: Record<string, unknown>;
  start_line?: number | null;
  end_line?: number | null;
  chunk_id?: number | null;
  document_file_path?: string | null;
  document_source_id?: number | string | null;
  document_start_line?: number | null;
  document_end_line?: number | null;
  document_page?: number | string | null;
  document_section?: string | null;
  document_url_anchor?: string | null;
  document_url?: string | null;
  code_file_path?: string | null;
  code_entity_id?: number | null;
  code_entity_name?: string | null;
  code_entity_type?: string | null;
  code_start_line?: number | null;
}

