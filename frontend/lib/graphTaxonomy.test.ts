import de from './i18n/de.json';
import en from './i18n/en.json';
import { describe, expect, it } from 'vitest';
import {
  EDGE_DIRECTION_TAXONOMY,
  EDGE_TYPE_COLORS,
  ENTITY_TYPE_LABELS,
  getEdgeTypeLabel,
  getEntityTypeLabel,
  getGraphEdgeColor,
  getGraphEdgeLabelKey,
  getGraphNodeCategory,
  getGraphNodeIconKind,
  getGraphNodeIconName,
  NODE_TYPE_TAXONOMY,
  normalizeGraphEdgeDirection,
} from './graphTaxonomy';

describe('graph taxonomy', () => {
  it('defines flow and arrowheads consistently for each edge direction', () => {
    expect(EDGE_DIRECTION_TAXONOMY.directed).toMatchObject({ flow: 'source_to_target', arrowheads: 1 });
    expect(EDGE_DIRECTION_TAXONOMY.undirected).toMatchObject({ flow: 'none', arrowheads: 0 });
    expect(EDGE_DIRECTION_TAXONOMY.bidirectional).toMatchObject({ flow: 'both', arrowheads: 2 });

    expect(normalizeGraphEdgeDirection('directed')).toBe('directed');
    expect(normalizeGraphEdgeDirection('undirected')).toBe('undirected');
    expect(normalizeGraphEdgeDirection('bidirectional')).toBe('bidirectional');
    expect(normalizeGraphEdgeDirection('unknown', 'directed')).toBe('directed');
    expect(normalizeGraphEdgeDirection(null)).toBe('undirected');
  });

  it('classifies Java entities and source-backed documents through the shared policy', () => {
    expect(getGraphNodeCategory({ type: 'insight' })).toBe('insight');
    expect(getGraphNodeCategory({ type: 'entity', entity_type: 'class' })).toBe('git');
    expect(getGraphNodeCategory({ type: 'entity', entity_type: 'copybook' })).toBe('copybook');
    expect(getGraphNodeCategory({ type: 'document', source_type: 'Git', file_path: 'A.java' })).toBe('git');
    expect(getGraphNodeCategory({ type: 'document', file_path: 'scanned-handbook.pdf' })).toBe('file');
    // Web-Systeme ohne eigenen Eintrag sind keine Dateien.
    expect(getGraphNodeCategory({ type: 'document', source_type: 'GitLabIssues', file_path: '1/issues/1' })).toBe('web');
    expect(getGraphNodeCategory({ type: 'document', source_type: 'Local', file_path: 'notes' })).toBe('file');
    expect(getGraphNodeIconKind({ type: 'entity', entity_type: 'record' })).toBe('code');
    expect(getGraphNodeIconKind({ type: 'document', url: 'https://example.test/page' })).toBe('web');
  });

  it('draws semantic relationships in their own mint color, apart from every other edge type', () => {
    const others = Object.entries(EDGE_TYPE_COLORS).filter(([type]) => type !== 'semantic').map(([, color]) => color);
    expect(getGraphEdgeColor('semantic')).toBe('rgb(var(--ds-graph-mint-base))');
    expect(others).not.toContain(getGraphEdgeColor('semantic'));
  });

  it('keeps manual links apart from the suggested keyword and semantic links', () => {
    expect(getGraphEdgeColor('manual')).not.toBe(getGraphEdgeColor('keyword'));
    expect(getGraphEdgeColor('manual')).not.toBe(getGraphEdgeColor('semantic'));
  });

  it('keeps unknown node and edge types usable with deterministic fallbacks', () => {
    expect(getGraphNodeCategory({ type: 'document', file_path: 'notes.custom' })).toBe('file');
    expect(getGraphNodeIconKind({ type: 'future-parser-node' })).toBe('document');
    expect(getGraphEdgeColor('FUTURE_RELATION')).toBe(getGraphEdgeColor('FUTURE_RELATION'));
    expect(getGraphEdgeColor('CALLS')).toBe(getGraphEdgeColor('calls'));
    expect(getGraphEdgeLabelKey('documented')).toBe('graphLabels.linkTypes.documented');
  });

  it('provides shared labels for known Java types and edge names', () => {
    expect(getEntityTypeLabel('record', 'de')).toBe('Record');
    expect(getEntityTypeLabel('record', 'en')).toBe('Record');
    expect(getEntityTypeLabel('future_entity', 'en')).toBe('Future entity');
    expect(getGraphEdgeLabelKey('EXTENDS')).toBe('graphLabels.linkTypes.extends');
    expect(getGraphEdgeLabelKey('uses_type')).toBe('graphLabels.linkTypes.usesType');
  });

  it('labels the structured companion languages as code instead of COBOL fallbacks', () => {
    expect(getEntityTypeLabel('xslt_template', 'de')).toBe('XSLT-Template');
    expect(getEntityTypeLabel('jsp_page', 'en')).toBe('JSP page');
    expect(getGraphNodeIconKind({ type: 'entity', entity_type: 'shell_script' })).toBe('code');
  });

  it('gives every node category its own icon and insights a light bulb', () => {
    const icons = Object.values(NODE_TYPE_TAXONOMY).map(type => type.icon);
    expect(new Set(icons).size).toBe(icons.length);
    expect(getGraphNodeIconName({ type: 'insight' })).toBe('insight');
    expect(getGraphNodeIconName({ type: 'entity', entity_type: 'copybook' })).toBe('copybook');
    expect(getGraphNodeIconName({ type: 'document', url: 'https://example.test/page' })).toBe('web');
    expect(getGraphNodeIconName({ type: 'document', file_path: 'notes.custom' })).toBe('file');
  });
});

describe('labels of parser types', () => {
  const dictionaries = { de, en } as const;
  const translator = (locale: 'de' | 'en') => (key: string) => {
    const value = key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], dictionaries[locale]);
    if (typeof value !== 'string') throw new Error(`missing ${locale} translation: ${key}`);
    return value;
  };

  // Alle Typen, die die Parser im Bestand erzeugt haben (Java, COBOL, JCL, XML, Maven, ...).
  const ENTITY_TYPES = ('property method parameter local_variable field class compilation_unit lambda doc_section anonymous_class constructor data_item '
    + 'xsd_element method_reference maven_dependency interface record_component configuration_file maven_source_root properties_file asciidoc_document '
    + 'xsd_attribute package xml_document maven_property spring_bean xsd_complex_type initializer record enum paragraph maven_project maven_module '
    + 'html_document endpoint maven_plugin local_class function annotation_type exec_operation exec_block jcl_dataset wsdl_part xsd_schema wsdl_message '
    + 'wsdl_operation jcl_step shell_function xsd_simple_type exec_resource xslt_template xslt_parameter groovy_file section sql_statement wsdl_port '
    + 'xslt_stylesheet xslt_variable xsd_attribute_group copybook jcl_file sql_object wsdl_binding shell_script jcl_job file_fd wsdl_service html_form '
    + 'wsdl_port_type program sql_script javascript_file xslt_section sql_block sql_include jcl_proc xsd_group sql_table entry '
    + 'bms_mapset bms_map bms_field').split(' ');
  const EDGE_TYPES = ('CALLS USES_TYPE READS IMPORTS INSTANTIATES WRITES EXTENDS DOCUMENTS CONTAINS IMPLEMENTS REFERENCES_METHOD REFERENCES_XML_ELEMENT DEPENDS_ON '
    + 'USES_XML_TYPE INCLUDES DECLARES_SOURCE_ROOT MAPS_XML_ELEMENT CONFIGURES INJECTS PERFORM CONTAINS_MODULE EXTENDS_XML_TYPE USES EXPOSES USES_PLUGIN EXECUTES '
    + 'REFERENCES_PROPERTY_KEY COPY MAPS_XML_TYPE LINKS_TO USES_RESOURCE GOTO DECLARES IMPLEMENTS_OPERATION BINDS_TO APPLIES_TEMPLATES DISPATCHES_TO CALL '
    + 'REFERENCES_RESOURCE INPUT_MESSAGE OUTPUT_MESSAGE CALLS_TEMPLATE SUBMITS_TO DEFINES ASSIGNED_DATASET USES_DATASET READS_XML FAULT_MESSAGE SOURCES '
    + 'EXECUTES_SCRIPT HANDLES_XML_ELEMENT USES_MAP').split(' ');

  it.each(['de', 'en'] as const)('names every known type in %s, never with the raw value', (locale) => {
    for (const type of ENTITY_TYPES) expect(ENTITY_TYPE_LABELS[type]?.[locale], type).toBeTruthy();
    for (const type of EDGE_TYPES) {
      expect(getGraphEdgeLabelKey(type), type).toBeTruthy();
      expect(getEdgeTypeLabel(type, translator(locale)), type).not.toContain('_');
    }
  });

  it('names a file, a variable and a method in both languages', () => {
    expect(getEntityTypeLabel('compilation_unit', 'de')).toBe('Datei');
    expect(getEntityTypeLabel('compilation_unit', 'en')).toBe('File');
    expect(getEntityTypeLabel('local_variable', 'de')).toBe('Variable');
    expect(getEntityTypeLabel('method', 'en')).toBe('Method');
    expect(getEdgeTypeLabel('USES_TYPE', translator('de'))).toBe('Verwendet Typ');
  });

  it('makes a type readable that the frontend does not know yet', () => {
    expect(getEdgeTypeLabel('NEW_EDGE_TYPE', translator('de'))).toBe('New edge type');
    expect(getEntityTypeLabel('new_entity_type', 'de')).toBe('New entity type');
  });
});
