import { describe, expect, it } from 'vitest';
import { resolveReferenceTarget } from './referenceTarget';

describe('resolveReferenceTarget', () => {
  it('matches prefixed local document paths and classifies them as documents', () => {
    expect(resolveReferenceTarget('123_manual.pdf#chunk-2', null, [
      { id: 8, type: 'local', name: 'manual.pdf' },
    ])).toMatchObject({ isDoc: true, isWebOrigin: false, resolvedSourceId: 8 });
  });

  it('classifies Confluence and Jira references as web origins', () => {
    expect(resolveReferenceTarget('https://docs.example.test/page', 9, [
      { id: 9, type: 'Confluence', name: 'Docs' },
    ])).toMatchObject({ isDoc: false, isWebOrigin: true, resolvedSourceId: 9 });
  });

  it('leaves ordinary code references without a matching source unresolved', () => {
    expect(resolveReferenceTarget('src/program.cbl#chunk-1', null, [])).toEqual({
      isDoc: false,
      isWebOrigin: false,
      resolvedSourceId: null,
    });
  });
});
