import type { SettingsContextValue } from '@/components/settings/SettingsContext';
import { vi } from 'vitest';

/**
 * Default-Zustand für `SettingsContextValue`, den jeder Component-Test unter
 * `settings/` und `settings/tabs/` als Grundlage für `vi.mock('@/components/settings/SettingsContext', ...)`
 * nutzen kann (O-102) — sonst erfindet jeder einzelne Tab-Test alle ~30 Felder
 * des Context neu. Ein Test überschreibt nur, was er tatsächlich braucht.
 */
export function createSettingsContextValue(
  overrides: Partial<SettingsContextValue> = {}
): SettingsContextValue {
  return {
    theme: 'dark',
    setTheme: vi.fn(),
    projects: [],
    setProjects: vi.fn(),
    selectedProject: null,
    setSelectedProject: vi.fn(),
    setFiles: vi.fn(),
    showToast: vi.fn(),
    backendStatus: 'online',

    activeLlmModel: 'mistral-nemo',
    setActiveLlmModel: vi.fn(),
    activeEmbeddingModel: 'bge-m3',
    setActiveEmbeddingModel: vi.fn(),
    availableModels: [],
    temperature: 0.7,
    setTemperature: vi.fn(),
    systemPrompt: '',
    setSystemPrompt: vi.fn(),
    llmProfiles: [],
    setLlmProfiles: vi.fn(),
    activeProfileId: '',
    setActiveProfileId: vi.fn(),
    embeddingProfiles: [],
    setEmbeddingProfiles: vi.fn(),
    activeEmbeddingProfileId: '',
    setActiveEmbeddingProfileId: vi.fn(),
    embeddingDimension: 1024,
    setEmbeddingDimension: vi.fn(),
    embeddingContextLength: 8192,
    setEmbeddingContextLength: vi.fn(),
    llmContextLength: 8192,
    setLlmContextLength: vi.fn(),

    editorFontSize: 14,
    setEditorFontSize: vi.fn(),
    editorMinimap: true,
    setEditorMinimap: vi.fn(),
    editorFontFamily: 'monospace',
    setEditorFontFamily: vi.fn(),

    workspaceSplit: 'horizontal',
    setWorkspaceSplit: vi.fn(),

    connectedSources: [],
    setConnectedSources: vi.fn(),
    projectStats: {},
    pinnedSourceIds: [],
    togglePinSource: vi.fn(),

    currentUser: { id: 1, username: 'admin', is_admin: true },

    ...overrides,
  };
}
