import { expect, it } from 'vitest';
import { knowledgeRelationshipKind } from './linkRelationshipKind';
import type { KnowledgeLinkSide } from './linkManagerTypes';

const doc: KnowledgeLinkSide = { type: 'document', title: 'README.md', url: null, source_type: 'Git' };

it('keeps repository documentation as documentation and recognizes code without navigation metadata', () => {
  const code = { ...doc, type: 'entity', title: 'Controller' };
  expect(knowledgeRelationshipKind(doc, doc)).toBe('docDoc');
  expect(knowledgeRelationshipKind(code, code)).toBe('codeCode');
  expect(knowledgeRelationshipKind(doc, code)).toBe('codeDoc');
});

it('recognizes a concrete code locator even if the side type is generic', () => {
  const code = { ...doc, code_ref: { file_path: 'Service.java', line: 1, source_id: 7 } };
  expect(knowledgeRelationshipKind(code, code)).toBe('codeCode');
});
