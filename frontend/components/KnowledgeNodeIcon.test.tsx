import { describe, expect, it } from 'vitest';
import { getKnowledgeNodeIconKind } from './KnowledgeNodeIcon';

describe('getKnowledgeNodeIconKind', () => {
  it('uses the code icon for entities and Git code nodes', () => {
    expect(getKnowledgeNodeIconKind({ type: 'entity' })).toBe('code');
    expect(getKnowledgeNodeIconKind({ type: 'document', source_type: 'Git' })).toBe('code');
    expect(getKnowledgeNodeIconKind({ node_type: 'entity', node_meta: { type: 'paragraph' } })).toBe('code');
  });

  it('uses the globe for web sources and web URLs', () => {
    expect(getKnowledgeNodeIconKind({ type: 'document', source_type: 'Confluence' })).toBe('web');
    expect(getKnowledgeNodeIconKind({ node_type: 'knowledge_source', node_meta: { type: 'Jira' } })).toBe('web');
    expect(getKnowledgeNodeIconKind({ type: 'document', url: 'https://example.test/page' })).toBe('web');
  });

  it('uses the document icon as the default', () => {
    expect(getKnowledgeNodeIconKind({ type: 'document', file_path: '/tmp/readme.md' })).toBe('document');
  });
});
