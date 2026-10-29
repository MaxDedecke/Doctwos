import { describe, expect, it } from 'vitest';
import {
  EDGE_DIRECTION_TAXONOMY,
  EDGE_TYPE_COLORS,
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
    expect(getEntityTypeLabel('future_entity', 'en')).toBe('future_entity');
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
