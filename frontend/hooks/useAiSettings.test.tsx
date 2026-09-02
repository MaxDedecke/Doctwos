import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { useAiSettings } from './useAiSettings';

vi.mock('@/app/services/api', () => ({
  api: {
    getModelInfo: vi.fn(),
    getModels: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);
const translate = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

describe('useAiSettings', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetAllMocks();
    mockedApi.getModelInfo.mockResolvedValue({ data: { llm: 'llama3', embedding: 'bge-m3' } } as never);
    mockedApi.getModels.mockResolvedValue({ data: { models: ['llama3', 'qwen'] } } as never);
  });

  it('migrates the legacy model settings and restores the active profile parameters', async () => {
    localStorage.setItem('doctus-llm-provider', 'openai');
    localStorage.setItem('doctus-llm-model', 'gpt-4o');
    localStorage.setItem('doctus-llm-api-key', 'secret');
    localStorage.setItem('doctus-llm-base-url', 'https://example.test');

    const { result } = renderHook(() => useAiSettings({ isLoggedIn: false, t: translate }));

    await waitFor(() => expect(result.current.llmProfiles).toHaveLength(2));
    expect(result.current.activeProfileId).toBe('ollama-default');
    expect(result.current.llmProfiles[1]).toMatchObject({
      provider: 'openai',
      model: 'gpt-4o',
      apiKey: 'secret',
      baseUrl: 'https://example.test',
    });
    expect(localStorage.getItem('doctus-active-profile-id')).toBe('ollama-default');
  });

  it('loads models only for an authenticated session and synchronizes profile parameters on switch', async () => {
    localStorage.setItem('doctus-llm-profiles', JSON.stringify([
      { id: 'one', name: 'One', provider: 'ollama', model: 'one', temperature: 0.2, systemPrompt: 'one prompt' },
      { id: 'two', name: 'Two', provider: 'ollama', model: 'two', temperature: 0.9, systemPrompt: 'two prompt' },
    ]));
    localStorage.setItem('doctus-active-profile-id', 'one');

    const { result } = renderHook(() => useAiSettings({ isLoggedIn: true, t: translate }));

    await waitFor(() => expect(result.current.availableModels).toEqual(['llama3', 'qwen']));
    expect(result.current.activeLlmModel).toBe('llama3');
    expect(result.current.activeEmbeddingModel).toBe('bge-m3');
    expect(result.current.temperature).toBe(0.2);
    expect(result.current.systemPrompt).toBe('one prompt');

    act(() => result.current.setActiveProfileId('two'));
    expect(result.current.activeProfileId).toBe('two');
    expect(result.current.temperature).toBe(0.9);
    expect(result.current.systemPrompt).toBe('two prompt');
    expect(localStorage.getItem('doctus-active-profile-id')).toBe('two');
    expect(mockedApi.getModelInfo).toHaveBeenCalledTimes(1);
    expect(mockedApi.getModels).toHaveBeenCalledTimes(1);
  });
});
