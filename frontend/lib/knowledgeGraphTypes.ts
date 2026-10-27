export interface GraphNode {
  id: string;
  type: 'entity' | 'code_file' | 'document' | 'copybook' | 'external';
  label: string;
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

