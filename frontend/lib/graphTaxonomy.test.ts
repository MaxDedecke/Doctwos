import { describe, expect, it } from 'vitest';
import {
  getEntityTypeLabel,
  getGraphEdgeColor,
  getGraphEdgeLabelKey,
  getGraphNodeCategory,
  getGraphNodeIconKind,
} from './graphTaxonomy';

describe('graph taxonomy', () => {
  it('classifies Java entities and source-backed documents through the shared policy', () => {
    expect(getGraphNodeCategory({ type: 'entity', entity_type: 'class' })).toBe('git');
    expect(getGraphNodeCategory({ type: 'entity', entity_type: 'copybook' })).toBe('copybook');
    expect(getGraphNodeCategory({ type: 'document', source_type: 'Git', file_path: 'A.java' })).toBe('git');
    expect(getGraphNodeIconKind({ type: 'entity', entity_type: 'record' })).toBe('code');
    expect(getGraphNodeIconKind({ type: 'document', url: 'https://example.test/page' })).toBe('web');
  });

  it('keeps unknown node and edge types usable with deterministic fallbacks', () => {
    expect(getGraphNodeCategory({ type: 'document', file_path: 'notes.custom' })).toBe('document');
    expect(getGraphNodeIconKind({ type: 'future-parser-node' })).toBe('document');
    expect(getGraphEdgeColor('FUTURE_RELATION')).toBe(getGraphEdgeColor('FUTURE_RELATION'));
    expect(getGraphEdgeColor('CALLS')).toBe(getGraphEdgeColor('calls'));
  });

  it('provides shared labels for known Java types and edge names', () => {
    expect(getEntityTypeLabel('record', 'de')).toBe('Record');
    expect(getEntityTypeLabel('record', 'en')).toBe('Record');
    expect(getEntityTypeLabel('future_entity', 'en')).toBe('future_entity');
    expect(getGraphEdgeLabelKey('EXTENDS')).toBe('graphLabels.linkTypes.extends');
    expect(getGraphEdgeLabelKey('uses_type')).toBe('graphLabels.linkTypes.usesType');
  });
});
