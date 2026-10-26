import type { DocLocation } from '@/lib/docLocation';

export interface CodeRef { file_path: string; line: number | null; source_id: number | string | null }

export interface EntityDocLink {
  id: number;
  entity_id: number;
  entity?: {
    id: number;
    name: string;
    type: string;
    file_path: string;
    start_line: number;
    end_line: number;
    source_id?: number | string | null;
  };
  doc_title: string;
  doc_url: string | null;
  // O-114: Wissensquelle der Doku-Seite — None bei manuell angelegten Links
  // ohne Chunk-Bezug, dann bleibt "Doku-Seite öffnen" aus.
  doc_source_id?: number | string | null;
  // Abschnitt/Seite/Zeilen der verknüpften Dokumentstelle (nur bei Verknüpfungen mit Chunk).
  doc_location?: DocLocation | null;
  source_type: string | null;
  score: number | null;
  link_type: string;
  direction?: 'directed' | 'undirected' | 'bidirectional';
  status: string;
  context: string | null;
  created_by: string;
}

export interface KnowledgeLinkSide {
  type: string;
  title: string;
  url: string | null;
  source_type: string | null;
  code_ref?: CodeRef | null;
  doc_source_id?: number | string | null;
  doc_location?: DocLocation | null;
}

export interface KnowledgeLink {
  id: number;
  source_a: KnowledgeLinkSide;
  source_b: KnowledgeLinkSide;
  score: number | null;
  link_type: string;
  direction?: 'directed' | 'undirected' | 'bidirectional';
  status: string;
  context: string | null;
  created_by: string;
}

export interface LinkCounts { pending: number; approved: number; rejected: number; }

