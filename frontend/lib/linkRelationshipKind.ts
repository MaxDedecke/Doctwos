import type { KnowledgeLinkSide } from './linkManagerTypes';

export type LinkRelationshipKind = 'codeCode' | 'codeDoc' | 'docDoc';
export type LinkKindFilter = 'all' | LinkRelationshipKind;

export function isCodeLinkSide(side: Pick<KnowledgeLinkSide, 'type' | 'code_ref'>): boolean {
  return side.type === 'entity' || Boolean(side.code_ref);
}

export function knowledgeRelationshipKind(a: KnowledgeLinkSide, b: KnowledgeLinkSide): LinkRelationshipKind {
  const codes = Number(isCodeLinkSide(a)) + Number(isCodeLinkSide(b));
  return codes === 2 ? 'codeCode' : codes === 1 ? 'codeDoc' : 'docDoc';
}
