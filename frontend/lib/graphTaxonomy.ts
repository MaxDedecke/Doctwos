/** Shared visual taxonomy for every graph-like view.
 *
 * Parser contracts intentionally use open strings.  This module owns the
 * presentation policy: known labels/colors/icons plus deterministic fallbacks
 * for types introduced by a parser that the frontend does not know yet.
 */

export type GraphIconKind = 'code' | 'document' | 'web';
/** One distinct glyph per node category; `web`/`code` cover nodes that only fall back to `file`. */
export type GraphNodeIconName =
  | 'insight' | 'cobol' | 'jcl' | 'copybook' | 'git' | 'external' | 'confluence' | 'jira'
  | 'pdf' | 'file' | 'txt' | 'md' | 'document' | 'web' | 'code' | 'group' | 'topic';
export type GraphLocale = 'de' | 'en';
export type GraphEdgeDirection = 'directed' | 'undirected' | 'bidirectional';

export interface GraphEdgeDirectionDefinition {
  labelKey: string;
  flow: 'source_to_target' | 'none' | 'both';
  arrowheads: 0 | 1 | 2;
}

/** Shared meaning of relationship direction across graph views and filters. */
export const EDGE_DIRECTION_TAXONOMY: Record<GraphEdgeDirection, GraphEdgeDirectionDefinition> = {
  directed: {
    labelKey: 'knowledgeGraphView.edgeDirection.directed',
    flow: 'source_to_target',
    arrowheads: 1,
  },
  undirected: {
    labelKey: 'knowledgeGraphView.edgeDirection.undirected',
    flow: 'none',
    arrowheads: 0,
  },
  bidirectional: {
    labelKey: 'knowledgeGraphView.edgeDirection.bidirectional',
    flow: 'both',
    arrowheads: 2,
  },
};

/** Normalize open API strings while retaining a caller-supplied legacy fallback. */
export function normalizeGraphEdgeDirection(
  value: unknown,
  fallback: GraphEdgeDirection = 'undirected',
): GraphEdgeDirection {
  if (typeof value === 'string' && Object.prototype.hasOwnProperty.call(EDGE_DIRECTION_TAXONOMY, value)) {
    return value as GraphEdgeDirection;
  }
  return fallback;
}

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
  group_kind?: unknown;
  topic_color?: unknown;
}

export interface GraphNodeTypeDefinition {
  labelDe: string;
  labelEn: string;
  color: string;
  icon: GraphNodeIconName;
}

export const NODE_TYPE_TAXONOMY: Record<string, GraphNodeTypeDefinition> = {
  insight: { labelDe: 'Erkenntnisse', labelEn: 'Insights', color: 'rgb(var(--ds-warning-base))', icon: 'insight' },
  group:      { labelDe: 'Gruppen (Kopplung)', labelEn: 'Groups (coupling)', color: 'rgb(var(--ds-success-strong))', icon: 'group' },
  topic:      { labelDe: 'Topics', labelEn: 'Topics', color: 'rgb(var(--ds-graph-a-base))', icon: 'topic' },
  cobol:      { labelDe: 'COBOL-Programme (.cbl/.cob)', labelEn: 'COBOL Programs (.cbl/.cob)', color: 'rgb(var(--ds-info-base))', icon: 'cobol' },
  pdf:        { labelDe: 'PDF-Dokumente (.pdf)', labelEn: 'PDF Documents (.pdf)', color: 'rgb(var(--ds-danger-base))', icon: 'pdf' },
  jcl:        { labelDe: 'JCL (.jcl/.proc)', labelEn: 'JCL (.jcl/.proc)', color: 'rgb(var(--ds-warning-base))', icon: 'jcl' },
  confluence: { labelDe: 'Confluence', labelEn: 'Confluence', color: 'rgb(var(--ds-info-base))', icon: 'confluence' },
  jira:       { labelDe: 'Jira Software', labelEn: 'Jira Software', color: 'rgb(var(--ds-accent))', icon: 'jira' },
  git:        { labelDe: 'Git / Code-Elemente', labelEn: 'Git / Code Elements', color: 'rgb(var(--ds-success-base))', icon: 'git' },
  file:       { labelDe: 'Datei', labelEn: 'File', color: 'rgb(var(--ds-danger-base))', icon: 'file' },
  txt:        { labelDe: 'Text-Dateien (.txt)', labelEn: 'Text Files (.txt)', color: 'rgb(var(--ds-neutral-500))', icon: 'txt' },
  md:         { labelDe: 'Markdown-Dateien (.md)', labelEn: 'Markdown Files (.md)', color: 'rgb(var(--ds-neutral-500))', icon: 'md' },
  copybook:   { labelDe: 'Copybook', labelEn: 'Copybook', color: 'rgb(var(--ds-graph-a-base))', icon: 'copybook' },
  external:   { labelDe: 'Externe Referenzen', labelEn: 'External References', color: 'rgb(var(--ds-neutral-500))', icon: 'external' },
  document:   { labelDe: 'Sonstige Dokumente', labelEn: 'Other Documents', color: 'rgb(var(--ds-neutral-300))', icon: 'document' },
};

/** Known entity names are labels only; unknown parser entity types remain valid. */
export const ENTITY_TYPE_LABELS: Record<string, { de: string; en: string }> = {
  compilation_unit: { de: 'Datei', en: 'File' },
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
  sql_include: { de: 'SQL-Include', en: 'SQL include' },
  parameter: { de: 'Parameter', en: 'Parameter' },
  record_component: { de: 'Record-Komponente', en: 'Record component' },
  local_variable: { de: 'Variable', en: 'Variable' },
  local_class: { de: 'Lokale Klasse', en: 'Local class' },
  anonymous_class: { de: 'Anonyme Klasse', en: 'Anonymous class' },
  lambda: { de: 'Lambda', en: 'Lambda' },
  method_reference: { de: 'Methodenreferenz', en: 'Method reference' },
  exec_block: { de: 'EXEC-Block', en: 'EXEC block' },
  exec_operation: { de: 'EXEC-Operation', en: 'EXEC operation' },
  exec_resource: { de: 'EXEC-Ressource', en: 'EXEC resource' },
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
  asciidoc_document: { de: 'AsciiDoc-Dokument', en: 'AsciiDoc document' },
  doc_section: { de: 'Doku-Abschnitt', en: 'Doc section' },
  shell_script: { de: 'Shell-Skript', en: 'Shell script' },
  shell_function: { de: 'Shell-Funktion', en: 'Shell function' },
  jcl_job: { de: 'JCL-Job', en: 'JCL job' },
  jcl_step: { de: 'JCL-Schritt', en: 'JCL step' },
  jcl_file: { de: 'JCL-Datei', en: 'JCL file' },
  jcl_proc: { de: 'JCL-Prozedur', en: 'JCL procedure' },
  jcl_dataset: { de: 'JCL-Dataset', en: 'JCL dataset' },
  cics_file: { de: 'CICS-Datei', en: 'CICS file' },
  csd_file: { de: 'CICS-Ressourcendefinition', en: 'CICS resource definition' },
  configuration_file: { de: 'Konfigurationsdatei', en: 'Configuration file' },
  endpoint: { de: 'Endpunkt', en: 'Endpoint' },
  function: { de: 'Funktion', en: 'Function' },
  groovy_file: { de: 'Groovy-Datei', en: 'Groovy file' },
  javascript_file: { de: 'JavaScript-Datei', en: 'JavaScript file' },
  maven_dependency: { de: 'Maven-Abhängigkeit', en: 'Maven dependency' },
  maven_module: { de: 'Maven-Modul', en: 'Maven module' },
  maven_plugin: { de: 'Maven-Plugin', en: 'Maven plugin' },
  maven_project: { de: 'Maven-Projekt', en: 'Maven project' },
  maven_property: { de: 'Maven-Eigenschaft', en: 'Maven property' },
  maven_source_root: { de: 'Maven-Quellverzeichnis', en: 'Maven source root' },
  properties_file: { de: 'Properties-Datei', en: 'Properties file' },
  property: { de: 'Eigenschaft', en: 'Property' },
  spring_bean: { de: 'Spring-Bean', en: 'Spring bean' },
  sql_object: { de: 'SQL-Objekt', en: 'SQL object' },
  sql_script: { de: 'SQL-Skript', en: 'SQL script' },
  sql_statement: { de: 'SQL-Anweisung', en: 'SQL statement' },
  wsdl_binding: { de: 'WSDL-Binding', en: 'WSDL binding' },
  wsdl_message: { de: 'WSDL-Nachricht', en: 'WSDL message' },
  wsdl_operation: { de: 'WSDL-Operation', en: 'WSDL operation' },
  wsdl_part: { de: 'WSDL-Teil', en: 'WSDL part' },
  wsdl_port: { de: 'WSDL-Port', en: 'WSDL port' },
  wsdl_port_type: { de: 'WSDL-Port-Typ', en: 'WSDL port type' },
  wsdl_service: { de: 'WSDL-Service', en: 'WSDL service' },
  xsd_attribute: { de: 'XSD-Attribut', en: 'XSD attribute' },
  xsd_attribute_group: { de: 'XSD-Attributgruppe', en: 'XSD attribute group' },
  xsd_complex_type: { de: 'XSD-Komplextyp', en: 'XSD complex type' },
  xsd_element: { de: 'XSD-Element', en: 'XSD element' },
  xsd_group: { de: 'XSD-Gruppe', en: 'XSD group' },
  xsd_schema: { de: 'XSD-Schema', en: 'XSD schema' },
  xsd_simple_type: { de: 'XSD-Einfachtyp', en: 'XSD simple type' },
  xslt_parameter: { de: 'XSLT-Parameter', en: 'XSLT parameter' },
  xslt_variable: { de: 'XSLT-Variable', en: 'XSLT variable' },
};

/** Link colors are shared by the knowledge graph, call graph and detail panes. */
export const EDGE_TYPE_COLORS: Record<string, string> = {
  code_dependency: 'rgb(var(--ds-info-base))',
  semantic: 'rgb(var(--ds-graph-mint-base))',
  keyword: 'rgb(var(--ds-warning-base))',
  documented: 'rgb(var(--ds-danger-base))',
  syntactic: 'rgb(var(--ds-success-base))',
  coref: 'rgb(var(--ds-graph-b-base))',
  // Von Menschen gesetzt: eigene Farbe, nicht die der Stichwort-Vorschläge.
  manual: 'rgb(var(--ds-graph-a-base))',
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
  EXECUTES: 'rgb(var(--ds-danger-base))',
  USES_DATASET: 'rgb(var(--ds-info-base))',
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
  EXECUTES: 'graphLabels.linkTypes.executes',
  USES_DATASET: 'graphLabels.linkTypes.usesDataset',
  DOCUMENTS: 'graphLabels.linkTypes.documents',
  INCLUDES: 'graphLabels.linkTypes.includesDoc',
  APPLIES_TEMPLATES: 'graphLabels.linkTypes.appliesTemplates',
  ASSIGNED_DATASET: 'graphLabels.linkTypes.assignedDataset',
  BINDS_TO: 'graphLabels.linkTypes.bindsTo',
  CALLS_TEMPLATE: 'graphLabels.linkTypes.callsTemplate',
  CONFIGURES: 'graphLabels.linkTypes.configures',
  CONTAINS_MODULE: 'graphLabels.linkTypes.containsModule',
  DECLARES: 'graphLabels.linkTypes.declares',
  DECLARES_SOURCE_ROOT: 'graphLabels.linkTypes.declaresSourceRoot',
  DEFINES: 'graphLabels.linkTypes.defines',
  DEPENDS_ON: 'graphLabels.linkTypes.dependsOn',
  DISPATCHES_TO: 'graphLabels.linkTypes.dispatchesTo',
  EXECUTES_SCRIPT: 'graphLabels.linkTypes.executesScript',
  EXPOSES: 'graphLabels.linkTypes.exposes',
  EXTENDS_XML_TYPE: 'graphLabels.linkTypes.extendsXmlType',
  FAULT_MESSAGE: 'graphLabels.linkTypes.faultMessage',
  HANDLES_XML_ELEMENT: 'graphLabels.linkTypes.handlesXmlElement',
  IMPLEMENTS_OPERATION: 'graphLabels.linkTypes.implementsOperation',
  INJECTS: 'graphLabels.linkTypes.injects',
  INPUT_MESSAGE: 'graphLabels.linkTypes.inputMessage',
  LINKS_TO: 'graphLabels.linkTypes.linksTo',
  MAPS_XML_ELEMENT: 'graphLabels.linkTypes.mapsXmlElement',
  MAPS_XML_TYPE: 'graphLabels.linkTypes.mapsXmlType',
  OUTPUT_MESSAGE: 'graphLabels.linkTypes.outputMessage',
  READS_XML: 'graphLabels.linkTypes.readsXml',
  REFERENCES_METHOD: 'graphLabels.linkTypes.referencesMethod',
  REFERENCES_PROPERTY_KEY: 'graphLabels.linkTypes.referencesPropertyKey',
  REFERENCES_RESOURCE: 'graphLabels.linkTypes.referencesResource',
  REFERENCES_XML_ELEMENT: 'graphLabels.linkTypes.referencesXmlElement',
  SOURCES: 'graphLabels.linkTypes.sources',
  SUBMITS_TO: 'graphLabels.linkTypes.submitsTo',
  USES: 'graphLabels.linkTypes.uses',
  USES_PLUGIN: 'graphLabels.linkTypes.usesPlugin',
  USES_RESOURCE: 'graphLabels.linkTypes.usesResource',
  USES_XML_TYPE: 'graphLabels.linkTypes.usesXmlType',
};

const CODE_ENTITY_TYPES = new Set([
  'program', 'copybook', 'section', 'paragraph', 'data_item', 'file_fd',
  'sql_table', 'sql_block', 'entry', 'compilation_unit', 'package', 'module',
  'class', 'interface', 'enum', 'record', 'annotation_type', 'method',
  'constructor', 'field', 'enum_constant', 'initializer', 'jcl_job', 'jcl_step',
  'jcl_file', 'jcl_proc', 'jcl_dataset',
  'parameter', 'record_component', 'local_variable', 'local_class', 'anonymous_class',
  'lambda', 'method_reference',
  'xslt_stylesheet', 'xslt_template', 'xslt_section', 'xml_document', 'jsp_page',
  'jsp_taglib', 'jsp_scriptlet', 'jsp_el_expression', 'html_document', 'html_form',
  'shell_script', 'shell_function',
]);

/** Dokumentations-Objekte (AsciiDoc): keine Code-Objekte, z. B. nicht im Code-Picker des Link Managers. */
export const DOCUMENTATION_ENTITY_TYPES = new Set(['asciidoc_document', 'doc_section']);

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
    nodeType === 'entity' || nodeType === 'code_file' || nodeType === 'code' || nodeType === 'cobol' ||
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
  if (nodeType === 'insight') return 'insight';
  if (nodeType === 'group') return textValue(node.group_kind) === 'topic' ? 'topic' : 'group';
  if (nodeType === 'code_file') {
    const path = String(node.file_path || node.label || '').toLowerCase();
    if (/\.(cbl|cob|cobol)$/.test(path)) return 'cobol';
    if (/\.(cpy|copy)$/.test(path)) return 'copybook';
    if (/\.(jcl|proc|prc)$/.test(path)) return 'jcl';
    return 'git';
  }
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

/** Category glyph; uncategorized files keep the web/code distinction of the icon family. */
export function getGraphNodeIconName(node: GraphTaxonomyNode | null | undefined, category = getGraphNodeCategory(node)): GraphNodeIconName {
  if (category === 'file') {
    const kind = getGraphNodeIconKind(node);
    if (kind !== 'document') return kind;
  }
  return NODE_TYPE_TAXONOMY[category]?.icon ?? 'file';
}

/** Colors a topic can be given in the topics panel, as design tokens. */
const TOPIC_COLORS: Record<string, string> = {
  indigo: 'rgb(var(--ds-accent))',
  emerald: 'rgb(var(--ds-success-base))',
  amber: 'rgb(var(--ds-warning-base))',
  rose: 'rgb(var(--ds-danger-base))',
  violet: 'rgb(var(--ds-graph-a-base))',
  sky: 'rgb(var(--ds-info-base))',
  orange: 'rgb(var(--ds-warning-strong))',
};

export function getGraphNodeColor(node: GraphTaxonomyNode | null | undefined): string {
  const category = getGraphNodeCategory(node);
  const topicColor = category === 'topic' ? TOPIC_COLORS[textValue(node?.topic_color)] : undefined;
  return topicColor || NODE_TYPE_TAXONOMY[category]?.color || 'rgb(var(--ds-neutral-300))';
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

/** Für Typen, die ein Parser neu liefert: `NEW_EDGE_TYPE` wird „New edge type“. */
export function humanizeType(type: string): string {
  const words = type.replace(/_/g, ' ').toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function getEntityTypeLabel(type: string | null | undefined, locale: GraphLocale): string {
  if (!type) return '';
  return ENTITY_TYPE_LABELS[type]?.[locale] || humanizeType(type);
}

export function getEdgeTypeLabel(type: string | null | undefined, t: (key: string) => string): string {
  if (!type) return '';
  const key = getGraphEdgeLabelKey(type);
  return key ? t(key) : humanizeType(type);
}
