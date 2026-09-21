/** Shared visual taxonomy for every graph-like view.
 *
 * Parser contracts intentionally use open strings.  This module owns the
 * presentation policy: known labels/colors/icons plus deterministic fallbacks
 * for types introduced by a parser that the frontend does not know yet.
 */

export type GraphIconKind = 'code' | 'document' | 'web';
export type GraphLocale = 'de' | 'en';

export interface GraphTaxonomyNode {
  node_type?: unknown;
  type?: unknown;
  kind?: unknown;
  label?: unknown;
  entity_type?: unknown;
  entityType?: unknown;
  source_type?: unknown;
  sourceType?: unknown;
  url?: unknown;
  node_url?: unknown;
  nodeUrl?: unknown;
  node_meta?: Record<string, unknown> | null;
  meta?: Record<string, unknown> | null;
  file_path?: string;
}

export interface GraphNodeTypeDefinition {
  labelDe: string;
  labelEn: string;
  color: string;
  icon: GraphIconKind;
}

export const NODE_TYPE_TAXONOMY: Record<string, GraphNodeTypeDefinition> = {
  cobol:      { labelDe: 'COBOL-Programme (.cbl/.cob)', labelEn: 'COBOL Programs (.cbl/.cob)', color: 'rgb(var(--ds-info-base))', icon: 'code' },
  pdf:        { labelDe: 'PDF-Dokumente (.pdf)', labelEn: 'PDF Documents (.pdf)', color: 'rgb(var(--ds-danger-base))', icon: 'document' },
  jcl:        { labelDe: 'JCL (.jcl/.proc)', labelEn: 'JCL (.jcl/.proc)', color: 'rgb(var(--ds-warning-base))', icon: 'code' },
  confluence: { labelDe: 'Confluence', labelEn: 'Confluence', color: 'rgb(var(--ds-info-base))', icon: 'web' },
  jira:       { labelDe: 'Jira Software', labelEn: 'Jira Software', color: 'rgb(var(--ds-accent))', icon: 'web' },
  git:        { labelDe: 'Git / Code-Elemente', labelEn: 'Git / Code Elements', color: 'rgb(var(--ds-success-base))', icon: 'code' },
  file:       { labelDe: 'Datei', labelEn: 'File', color: 'rgb(var(--ds-danger-base))', icon: 'document' },
  txt:        { labelDe: 'Text-Dateien (.txt)', labelEn: 'Text Files (.txt)', color: 'rgb(var(--ds-neutral-500))', icon: 'document' },
  md:         { labelDe: 'Markdown-Dateien (.md)', labelEn: 'Markdown Files (.md)', color: 'rgb(var(--ds-neutral-500))', icon: 'document' },
  copybook:   { labelDe: 'Copybook', labelEn: 'Copybook', color: 'rgb(var(--ds-graph-a-base))', icon: 'code' },
  external:   { labelDe: 'Externe Referenzen', labelEn: 'External References', color: 'rgb(var(--ds-neutral-500))', icon: 'document' },
  document:   { labelDe: 'Sonstige Dokumente', labelEn: 'Other Documents', color: 'rgb(var(--ds-neutral-300))', icon: 'document' },
};

/** Known entity names are labels only; unknown parser entity types remain valid. */
export const ENTITY_TYPE_LABELS: Record<string, { de: string; en: string }> = {
  compilation_unit: { de: 'Datei', en: 'Compilation unit' },
  package: { de: 'Paket', en: 'Package' },
  module: { de: 'Modul', en: 'Module' },
  program: { de: 'Programm', en: 'Program' },
  copybook: { de: 'Copybook', en: 'Copybook' },
  section: { de: 'Section', en: 'Section' },
  paragraph: { de: 'Paragraph', en: 'Paragraph' },
  data_item: { de: 'Datenfeld', en: 'Data item' },
  file_fd: { de: 'Dateibeschreibung', en: 'File description' },
  sql_table: { de: 'SQL-Tabelle', en: 'SQL table' },
  sql_block: { de: 'SQL-Block', en: 'SQL block' },
  entry: { de: 'Entry', en: 'Entry' },
  class: { de: 'Klasse', en: 'Class' },
  interface: { de: 'Interface', en: 'Interface' },
  enum: { de: 'Enum', en: 'Enum' },
  record: { de: 'Record', en: 'Record' },
  annotation_type: { de: 'Annotation', en: 'Annotation type' },
  method: { de: 'Methode', en: 'Method' },
  constructor: { de: 'Konstruktor', en: 'Constructor' },
  field: { de: 'Feld', en: 'Field' },
  enum_constant: { de: 'Enum-Konstante', en: 'Enum constant' },
  initializer: { de: 'Initializer', en: 'Initializer' },
  xslt_stylesheet: { de: 'XSLT-Stylesheet', en: 'XSLT stylesheet' },
  xslt_template: { de: 'XSLT-Template', en: 'XSLT template' },
  xslt_section: { de: 'XSLT-Abschnitt', en: 'XSLT section' },
  xml_document: { de: 'XML-Dokument', en: 'XML document' },
  jsp_page: { de: 'JSP-Seite', en: 'JSP page' },
  jsp_taglib: { de: 'JSP-Tag-Bibliothek', en: 'JSP tag library' },
  jsp_scriptlet: { de: 'JSP-Scriptlet', en: 'JSP scriptlet' },
  jsp_el_expression: { de: 'JSP-EL-Ausdruck', en: 'JSP EL expression' },
  html_document: { de: 'HTML-Dokument', en: 'HTML document' },
  html_form: { de: 'HTML-Formular', en: 'HTML form' },
  shell_script: { de: 'Shell-Skript', en: 'Shell script' },
  shell_function: { de: 'Shell-Funktion', en: 'Shell function' },
  jcl_job: { de: 'JCL-Job', en: 'JCL job' },
  jcl_step: { de: 'JCL-Schritt', en: 'JCL step' },
};

/** Link colors are shared by the knowledge graph, call graph and detail panes. */
export const EDGE_TYPE_COLORS: Record<string, string> = {
  code_dependency: 'rgb(var(--ds-info-base))',
  semantic: 'rgb(var(--ds-accent))',
  keyword: 'rgb(var(--ds-warning-base))',
  documented: 'rgb(var(--ds-danger-base))',
  syntactic: 'rgb(var(--ds-success-base))',
  coref: 'rgb(var(--ds-graph-b-base))',
  manual: 'rgb(var(--ds-warning-base))',
  chat: 'rgb(var(--ds-info-base))',
  call: 'rgb(var(--ds-danger-base))',
  perform: 'rgb(var(--ds-success-base))',
  goto: 'rgb(var(--ds-warning-base))',
  copy: 'rgb(var(--ds-graph-a-base))',
  use: 'rgb(var(--ds-info-base))',
  CALL: 'rgb(var(--ds-danger-base))',
  PERFORM: 'rgb(var(--ds-success-base))',
  GOTO: 'rgb(var(--ds-warning-base))',
  COPY: 'rgb(var(--ds-graph-a-base))',
  CONTAINS: 'rgb(var(--ds-graph-b-base))',
  CALLS: 'rgb(var(--ds-danger-base))',
  INSTANTIATES: 'rgb(var(--ds-info-base))',
  EXTENDS: 'rgb(var(--ds-accent))',
  IMPLEMENTS: 'rgb(var(--ds-success-base))',
};

const EDGE_COLOR_FALLBACKS = [
  'rgb(var(--ds-info-base))',
  'rgb(var(--ds-graph-a-base))',
  'rgb(var(--ds-graph-b-base))',
  'rgb(var(--ds-warning-base))',
];

const EDGE_TYPE_LABEL_KEYS: Record<string, string> = {
  code_dependency: 'graphLabels.linkTypes.codeDependency',
  semantic: 'graphLabels.linkTypes.semantic',
  keyword: 'graphLabels.linkTypes.keyword',
  syntactic: 'graphLabels.linkTypes.syntactic',
  coref: 'graphLabels.linkTypes.coref',
  manual: 'graphLabels.linkTypes.manual',
  documented: 'graphLabels.linkTypes.documented',
  chat: 'graphLabels.linkTypes.chat',
  call: 'graphLabels.linkTypes.call',
  perform: 'graphLabels.linkTypes.perform',
  goto: 'graphLabels.linkTypes.goto',
  copy: 'graphLabels.linkTypes.copy',
  use: 'graphLabels.linkTypes.use',
  contains: 'graphLabels.linkTypes.contains',
  CALL: 'graphLabels.linkTypes.call',
  PERFORM: 'graphLabels.linkTypes.perform',
  GOTO: 'graphLabels.linkTypes.goto',
  COPY: 'graphLabels.linkTypes.copy',
  CONTAINS: 'graphLabels.linkTypes.contains',
  CALLS: 'graphLabels.linkTypes.calls',
  INSTANTIATES: 'graphLabels.linkTypes.instantiates',
  EXTENDS: 'graphLabels.linkTypes.extends',
  IMPLEMENTS: 'graphLabels.linkTypes.implements',
  USES_TYPE: 'graphLabels.linkTypes.usesType',
  IMPORTS: 'graphLabels.linkTypes.imports',
  READS: 'graphLabels.linkTypes.reads',
  WRITES: 'graphLabels.linkTypes.writes',
};

const CODE_ENTITY_TYPES = new Set([
  'program', 'copybook', 'section', 'paragraph', 'data_item', 'file_fd',
  'sql_table', 'sql_block', 'entry', 'compilation_unit', 'package', 'module',
  'class', 'interface', 'enum', 'record', 'annotation_type', 'method',
  'constructor', 'field', 'enum_constant', 'initializer', 'jcl_job', 'jcl_step',
  'xslt_stylesheet', 'xslt_template', 'xslt_section', 'xml_document', 'jsp_page',
  'jsp_taglib', 'jsp_scriptlet', 'jsp_el_expression', 'html_document', 'html_form',
  'shell_script', 'shell_function',
]);

const WEB_SOURCE_TYPES = new Set([
  'confluence', 'jira', 'web', 'webpage', 'webdav', 'url', 'http', 'https',
]);

function textValue(value: unknown): string {
  return typeof value === 'string' ? value.toLowerCase() : '';
}

/** Classify the icon family used by graph, search, topics and link-manager. */
export function getGraphNodeIconKind(node: GraphTaxonomyNode | null | undefined): GraphIconKind {
  if (!node) return 'document';

  const nodeType = textValue(node.node_type || node.type || node.kind);
  const entityType = textValue(node.entity_type || node.entityType);
  const meta = node.node_meta || node.meta || {};
  const metaType = textValue(meta.type || meta.source_type || meta.sourceType);
  const sourceType = textValue(
    node.source_type || node.sourceType || meta.source_type || meta.sourceType ||
    (nodeType === 'knowledge_source' ? meta.type : ''),
  );
  const url = node.url || node.node_url || node.nodeUrl;

  if (
    nodeType === 'entity' || nodeType === 'code' || nodeType === 'cobol' ||
    nodeType === 'jcl' || nodeType === 'git' || nodeType === 'copybook' ||
    nodeType === 'external' || CODE_ENTITY_TYPES.has(entityType)
  ) return 'code';
  if (sourceType === 'git' || metaType === 'git') return 'code';
  if (WEB_SOURCE_TYPES.has(sourceType) || WEB_SOURCE_TYPES.has(metaType)) return 'web';
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) return 'web';
  return 'document';
}

/** Resolve the broad node category used for filtering and coloring. */
export function getGraphNodeCategory(node: GraphTaxonomyNode | null | undefined): string {
  if (!node) return 'document';
  const nodeType = textValue(node.type || node.node_type || node.kind);
  const entityType = textValue(node.entity_type || node.entityType);
  if (nodeType === 'entity') return entityType === 'copybook' ? 'copybook' : 'git';
  if (nodeType === 'copybook') return 'copybook';
  if (nodeType === 'external') return 'external';

  const source = textValue(node.source_type || node.sourceType);
  if (source === 'confluence') return 'confluence';
  if (source === 'jira') return 'jira';
  if (source === 'git') return 'git';

  const path = String(node.file_path || node.url || node.label || '').toLowerCase();
  if (/\.(cbl|cob|cobol)$/.test(path)) return 'cobol';
  if (/\.(cpy|copy)$/.test(path)) return 'copybook';
  if (/\.(jcl|proc|prc)$/.test(path)) return 'jcl';
  if (path.endsWith('.pdf') || path.endsWith('.txt') || path.endsWith('.md')) return 'file';
  // Non-web DocumentChunks are files from the user's indexed sources. Keep
  // them in one filter group so a PDF is not hidden behind a format-specific
  // badge that users do not know to look for.
  return 'file';
}

export function getGraphNodeColor(node: GraphTaxonomyNode | null | undefined): string {
  return NODE_TYPE_TAXONOMY[getGraphNodeCategory(node)]?.color || 'rgb(var(--ds-neutral-300))';
}

/** Stable color for an arbitrary relationship type. */
export function getGraphEdgeColor(type: string | null | undefined): string {
  const value = type || '';
  if (EDGE_TYPE_COLORS[value]) return EDGE_TYPE_COLORS[value];
  const lower = value.toLowerCase();
  if (EDGE_TYPE_COLORS[lower]) return EDGE_TYPE_COLORS[lower];
  const upper = value.toUpperCase();
  if (EDGE_TYPE_COLORS[upper]) return EDGE_TYPE_COLORS[upper];
  let hash = 0;
  for (const char of upper) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return EDGE_COLOR_FALLBACKS[Math.abs(hash) % EDGE_COLOR_FALLBACKS.length];
}

export function getGraphEdgeLabelKey(type: string): string | undefined {
  return EDGE_TYPE_LABEL_KEYS[type] || EDGE_TYPE_LABEL_KEYS[type.toLowerCase()] || EDGE_TYPE_LABEL_KEYS[type.toUpperCase()];
}

export function getEntityTypeLabel(type: string | null | undefined, locale: GraphLocale): string {
  if (!type) return '';
  return ENTITY_TYPE_LABELS[type]?.[locale] || type;
}
