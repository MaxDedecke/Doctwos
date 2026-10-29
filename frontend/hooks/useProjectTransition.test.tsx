import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ChatSession } from '@/types/domain';
import { useProjectTransition } from './useProjectTransition';

function setup(overrides: { selectedProjectId?: number | null; sessionProjectId?: number | null } = {}) {
  const calls: string[] = [];
  const record = (name: string) => vi.fn(() => { calls.push(name); });
  const options = {
    selectedProject: overrides.selectedProjectId === null ? null : { id: overrides.selectedProjectId ?? 1, name: 'A' },
    sessions: [{ id: 7, project_id: overrides.sessionProjectId ?? 1 } as ChatSession],
    activeSessionId: 7,
    selectProject: vi.fn(async () => { calls.push('selectProject'); }),
    startNewChat: record('startNewChat'),
    resetChatSession: record('resetChatSession'),
    clearSelection: record('clearSelection'),
    clearFileReferences: record('clearFileReferences'),
    invalidateFileContent: record('invalidateFileContent'),
    onGeneralContext: record('onGeneralContext'),
    onStillAnalyzing: record('onStillAnalyzing'),
  };
  const { result } = renderHook(() => useProjectTransition(options));
  return { change: result.current, calls, options };
}

describe('useProjectTransition', () => {
  it('drops everything of the old project before the new one is set, from every entry point', async () => {
    for (const chat of ['new', 'reset-if-foreign', 'keep'] as const) {
      const { change, calls } = setup();
      await act(async () => { await change({ id: 2, name: 'B' }, { chat }); });
      const before = calls.slice(0, calls.indexOf('selectProject'));
      expect(before).toEqual(expect.arrayContaining(['invalidateFileContent', 'clearFileReferences', 'clearSelection']));
      expect(calls.at(-1)).toBe('selectProject');
    }
  });

  it('handles the chat by entry point: new chat, reset only for a foreign session, or keep it', async () => {
    const header = setup();
    await act(async () => { await header.change({ id: 2, name: 'B' }, { chat: 'new' }); });
    expect(header.calls).toContain('startNewChat');

    const search = setup({ sessionProjectId: 1 });
    await act(async () => { await search.change({ id: 2, name: 'B' }, { chat: 'reset-if-foreign' }); });
    expect(search.calls).toContain('resetChatSession');

    const sameSession = setup({ sessionProjectId: 2 });
    await act(async () => { await sameSession.change({ id: 2, name: 'B' }, { chat: 'reset-if-foreign' }); });
    expect(sameSession.calls).not.toContain('resetChatSession');

    const session = setup();
    await act(async () => { await session.change({ id: 2, name: 'B' }, { chat: 'keep' }); });
    expect(session.calls).not.toContain('resetChatSession');
    expect(session.calls).not.toContain('startNewChat');
  });

  it('changes nothing for the same project or one that is still being analysed', async () => {
    const same = setup();
    await act(async () => { await same.change({ id: 1, name: 'A' }, { chat: 'new' }); });
    expect(same.calls).toEqual([]);

    const analysing = setup();
    await act(async () => { await analysing.change({ id: 2, name: 'B', url: 'git@x', status: 'parsing' }, { chat: 'new' }); });
    expect(analysing.calls).toEqual(['onStillAnalyzing']);
  });

  it('switches to the general context with the same clean-up', async () => {
    const { change, calls } = setup();
    await act(async () => { await change(null, { chat: 'reset-if-foreign' }); });
    expect(calls).toEqual(['resetChatSession', 'invalidateFileContent', 'clearFileReferences', 'clearSelection', 'selectProject', 'onGeneralContext']);
  });
});
