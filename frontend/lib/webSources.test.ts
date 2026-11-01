import { describe, expect, it } from 'vitest';
import { isWebSourceType } from './webSources';
import { resolveReferenceTarget } from './referenceTarget';
import type { KnowledgeSource } from '@/types/domain';

describe('isWebSourceType', () => {
  it('treats everything except file sources as a web system, so new systems need no change here', () => {
    for (const type of ['Jira', 'confluence', 'ServiceNow', 'Notion']) expect(isWebSourceType(type)).toBe(true);
    for (const type of ['Git', 'local', 'FolderWatch', 'WebDAV', '', null, undefined]) expect(isWebSourceType(type)).toBe(false);
  });

  it('routes a reference of a new system to the web view', () => {
    const sources = [{ id: 7, type: 'ServiceNow', name: 'Snow' }, { id: 8, type: 'Git', name: 'Repo' }] as unknown as KnowledgeSource[];
    expect(resolveReferenceTarget('https://snow/i/1', 7, sources).isWebOrigin).toBe(true);
    expect(resolveReferenceTarget('src/a.cbl', 8, sources).isWebOrigin).toBe(false);
  });
});
