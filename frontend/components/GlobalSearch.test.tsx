/**
 * Regressionstest für O-038: das Speicher-Icon in der Header-Bar erscheint nur,
 * wenn der Chat leer ist UND eine zweite View offen ist -- sonst ist ein reiner
 * Graph-/Code-View-Befund ohne Chat-Nutzung nicht teil-/konservierbar, weil
 * eine Sitzung sonst erst mit der ersten Chat-Nachricht entsteht.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GlobalSearch } from './GlobalSearch';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';

function renderGlobalSearch(overrides: Partial<React.ComponentProps<typeof GlobalSearch>> = {}) {
  return render(
    <LanguageProvider>
      <GlobalSearch
        theme="dark"
        setTheme={vi.fn()}
        projects={[]}
        connectedSources={[]}
        onSelectResult={vi.fn()}
        isSidebarOpen={true}
        setIsSidebarOpen={vi.fn()}
        setIsSettingsOpen={vi.fn()}
        onOpenGraphView={vi.fn()}
        panelConfigs={['chat', 'graph']}
        onAddPanel={vi.fn()}
        selectedProject={null}
        onProjectSelect={vi.fn()}
        onShareChat={vi.fn()}
        canSaveSessionWithoutChat={false}
        onSaveSessionWithoutChat={vi.fn()}
        currentUser={null}
        {...overrides}
      />
    </LanguageProvider>
  );
}

describe('GlobalSearch save-session-without-chat button', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is hidden when the chat has messages or only one view is open', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue({ data: { jobs: [], active_count: 0 } } as any);
    renderGlobalSearch({ canSaveSessionWithoutChat: false });
    // LanguageProvider defaults to German (see LanguageContext.tsx) -- assert
    // on the real de.json string, not the translation key.
    expect(screen.queryByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)')).toBeNull();
  });

  it('appears when the chat is empty and a second view is open, and opens the naming dialog', () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue({ data: { jobs: [], active_count: 0 } } as any);
    renderGlobalSearch({ canSaveSessionWithoutChat: true });

    const button = screen.getByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)');
    expect(button).toBeTruthy();

    fireEvent.click(button);
    expect(screen.getByPlaceholderText('Name der Sitzung')).toBeTruthy();
  });

  it('calls onSaveSessionWithoutChat with the trimmed title when confirmed', async () => {
    vi.spyOn(api, 'getJobs').mockResolvedValue({ data: { jobs: [], active_count: 0 } } as any);
    const onSaveSessionWithoutChat = vi.fn().mockResolvedValue(undefined);
    renderGlobalSearch({ canSaveSessionWithoutChat: true, onSaveSessionWithoutChat });

    fireEvent.click(screen.getByTitle('Sitzung speichern (Chat wurde noch nicht benutzt)'));
    const input = screen.getByPlaceholderText('Name der Sitzung');
    fireEvent.change(input, { target: { value: '  Graph-Befund  ' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Speichern'));
    });

    expect(onSaveSessionWithoutChat).toHaveBeenCalledWith('Graph-Befund');
  });
});
