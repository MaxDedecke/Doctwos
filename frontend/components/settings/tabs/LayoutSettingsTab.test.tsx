import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const { apiMocks, settingsState, languageState } = vi.hoisted(() => {
  const settingsState = {
    theme: 'dark' as 'dark' | 'light',
    setTheme: vi.fn(),
    showToast: vi.fn(),
    selectedProject: null as { id: number; name: string } | null,
    workspaceSplit: 'horizontal',
    setWorkspaceSplit: vi.fn(),
    editorFontSize: 14,
    setEditorFontSize: vi.fn(),
    editorFontFamily: "'JetBrains Mono', monospace",
    setEditorFontFamily: vi.fn(),
    editorMinimap: true,
    setEditorMinimap: vi.fn(),
  };
  const languageState = {
    language: 'de' as 'de' | 'en',
    setLanguage: vi.fn(),
    t: (key: string) => key,
  };
  return { settingsState, languageState, apiMocks: { fetch: vi.fn() } };
});

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsState }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => languageState }));

import { LayoutSettingsTab } from './LayoutSettingsTab';

/** Findet die Select-Trigger-Combobox, die zu diesem Label-Text gehört (analog AiSettingsTab.test.tsx). */
function comboboxForLabel(labelText: string): HTMLElement {
  return within(screen.getByText(labelText).closest('div')!).getByRole('combobox');
}

afterEach(() => {
  vi.clearAllMocks();
  Object.assign(settingsState, {
    theme: 'dark',
    selectedProject: null,
    workspaceSplit: 'horizontal',
    editorFontSize: 14,
    editorFontFamily: "'JetBrains Mono', monospace",
    editorMinimap: true,
  });
  languageState.language = 'de';
});

describe('LayoutSettingsTab Farbthema', () => {
  it('switches from dark to light and shows the light-mode toast', () => {
    render(<LayoutSettingsTab />);
    fireEvent.click(document.getElementById('theme-toggle-switch')!);

    expect(settingsState.setTheme).toHaveBeenCalledWith('light');
    expect(settingsState.showToast).toHaveBeenCalledWith('settings.toast.lightModeEnabled', 'success');
  });

  it('switches from light to dark and shows the dark-mode toast', () => {
    settingsState.theme = 'light';
    render(<LayoutSettingsTab />);
    fireEvent.click(document.getElementById('theme-toggle-switch')!);

    expect(settingsState.setTheme).toHaveBeenCalledWith('dark');
    expect(settingsState.showToast).toHaveBeenCalledWith('settings.toast.darkModeEnabled', 'success');
  });
});

describe('LayoutSettingsTab Sprache', () => {
  it('switches to English', () => {
    render(<LayoutSettingsTab />);
    fireEvent.click(document.getElementById('language-toggle-en')!);
    expect(languageState.setLanguage).toHaveBeenCalledWith('en');
  });

  it('switches back to German', () => {
    languageState.language = 'en';
    render(<LayoutSettingsTab />);
    fireEvent.click(document.getElementById('language-toggle-de')!);
    expect(languageState.setLanguage).toHaveBeenCalledWith('de');
  });
});

describe('LayoutSettingsTab Arbeitsbereich-Aufteilung (Nahtstelle zu useWorkspaceLayout, O-092)', () => {
  it('highlights the option matching the persisted setting and nothing else', () => {
    settingsState.workspaceSplit = '60/40';
    render(<LayoutSettingsTab />);

    const selected = screen.getByText('settings.layoutTab.splits.wideChat.label').closest('button')!;
    expect(selected.className).toContain('border-ds-indigo-500/40');
    const other = screen.getByText('settings.layoutTab.splits.standard.label').closest('button')!;
    expect(other.className).not.toContain('border-ds-indigo-500/40');
  });

  // useWorkspaceLayout hält für den Split-Prozentsatz eine eigene presetMap
  // mit genau diesen vier Schlüsseln ('40/60' | '45/55' | '50/50' | '60/40');
  // jede andere ID fällt dort still auf 45% zurück (siehe hooks/useWorkspaceLayout.ts).
  // Diese Nahtstelle wird hier verriegelt, damit eine umbenannte ID nicht
  // stillschweigend den Trenner nicht mehr bewegt (O-092).
  it.each([
    ['settings.layoutTab.splits.narrowChat.label', '40/60'],
    ['settings.layoutTab.splits.standard.label', '45/55'],
    ['settings.layoutTab.splits.even.label', '50/50'],
    ['settings.layoutTab.splits.wideChat.label', '60/40'],
  ])('selecting %s reports the id %s that useWorkspaceLayout expects', (label, id) => {
    render(<LayoutSettingsTab />);
    fireEvent.click(screen.getByText(label));
    expect(settingsState.setWorkspaceSplit).toHaveBeenCalledWith(id);
  });
});

describe('LayoutSettingsTab Editor-Einstellungen', () => {
  it('shows the persisted font size and lets you change it', () => {
    render(<LayoutSettingsTab />);
    expect(screen.getByText('14px')).toBeTruthy();

    fireEvent.click(comboboxForLabel('settings.editorTab.fontSizeLabel'));
    fireEvent.click(within(screen.getByRole('listbox')).getByText('18px'));

    expect(settingsState.setEditorFontSize).toHaveBeenCalledWith(18);
  });

  it('shows the persisted font family and lets you change it', () => {
    render(<LayoutSettingsTab />);
    expect(screen.getByText('JetBrains Mono')).toBeTruthy();

    fireEvent.click(comboboxForLabel('settings.editorTab.fontFamilyLabel'));
    fireEvent.click(within(screen.getByRole('listbox')).getByText('Fira Code'));

    expect(settingsState.setEditorFontFamily).toHaveBeenCalledWith("'Fira Code', monospace");
  });

  it('toggles the minimap', () => {
    render(<LayoutSettingsTab />);
    const minimapToggle = within(
      screen.getByText('settings.editorTab.minimapLabel').closest('div')!.parentElement as HTMLElement
    ).getByRole('button');

    fireEvent.click(minimapToggle);
    expect(settingsState.setEditorMinimap).toHaveBeenCalledWith(false);
  });
});

describe('LayoutSettingsTab Wissensgraph-Export', () => {
  let createdAnchor: HTMLAnchorElement | null;
  let anchorClick: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    createdAnchor = null;
    // jsdom kennt URL.createObjectURL nicht -- die beiden Methoden werden am
    // echten URL-Konstruktor ergänzt und danach wieder entfernt (analog
    // CallGraphView.test.tsx), damit URL selbst funktionsfähig bleibt.
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:layout'), revokeObjectURL: vi.fn() });
    anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      createdAnchor = this;
    });
  });

  afterEach(() => {
    anchorClick.mockRestore();
    Reflect.deleteProperty(URL, 'createObjectURL');
    Reflect.deleteProperty(URL, 'revokeObjectURL');
  });

  it("exports the Cypher script under the selected project's name", async () => {
    settingsState.selectedProject = { id: 7, name: 'Kernbanking' };
    apiMocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ cypher: 'CREATE (n)' }) });
    render(<LayoutSettingsTab />);

    fireEvent.click(screen.getByText('settings.layoutTab.graphExportCypherButton'));

    await waitFor(() => expect(anchorClick).toHaveBeenCalled());
    const url = apiMocks.fetch.mock.calls[0][0] as string;
    expect(url).toContain('/graph/export/neo4j?');
    expect(url).toContain('status=approved');
    expect(url).toContain('project_id=7');
    expect(createdAnchor!.download).toBe('knowledge_graph_Kernbanking.cypher');
  });

  it('falls back to "all" in the filename and omits project_id when no project is selected', async () => {
    apiMocks.fetch.mockResolvedValue({ ok: true, blob: async () => new Blob(['csv']) });
    render(<LayoutSettingsTab />);

    fireEvent.click(screen.getByText('settings.layoutTab.graphExportCsvButton'));

    await waitFor(() => expect(anchorClick).toHaveBeenCalled());
    const url = apiMocks.fetch.mock.calls[0][0] as string;
    expect(url).not.toContain('project_id');
    expect(createdAnchor!.download).toBe('knowledge_graph_all.csv');
  });

  it('exports GraphML with its own file extension', async () => {
    settingsState.selectedProject = { id: 3, name: 'Zahlungsverkehr' };
    apiMocks.fetch.mockResolvedValue({ ok: true, blob: async () => new Blob(['graphml']) });
    render(<LayoutSettingsTab />);

    fireEvent.click(screen.getByText('settings.layoutTab.graphExportGraphmlButton'));

    await waitFor(() => expect(anchorClick).toHaveBeenCalled());
    const url = apiMocks.fetch.mock.calls[0][0] as string;
    expect(url).toContain('format=graphml');
    expect(createdAnchor!.download).toBe('knowledge_graph_Zahlungsverkehr.graphml');
  });

  it('shows an error toast when the export request fails, without triggering a download', async () => {
    apiMocks.fetch.mockResolvedValue({ ok: false, status: 500 });
    render(<LayoutSettingsTab />);

    fireEvent.click(screen.getByText('settings.layoutTab.graphExportCsvButton'));

    await waitFor(() => expect(settingsState.showToast).toHaveBeenCalledWith('settings.layoutTab.exportError', 'error', expect.any(Error)));
    expect(anchorClick).not.toHaveBeenCalled();
  });

  it('shows an error toast when the export request throws', async () => {
    apiMocks.fetch.mockRejectedValue(new Error('network down'));
    render(<LayoutSettingsTab />);

    fireEvent.click(screen.getByText('settings.layoutTab.graphExportCypherButton'));

    await waitFor(() => expect(settingsState.showToast).toHaveBeenCalledWith('settings.layoutTab.exportError', 'error', expect.any(Error)));
  });
});
