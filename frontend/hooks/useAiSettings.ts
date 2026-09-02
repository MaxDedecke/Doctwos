import { useCallback, useEffect, useState } from 'react';
import { api } from '@/app/services/api';

export interface LlmProfile {
  id: string;
  name: string;
  provider: string;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  systemPrompt?: string;
}

type Translator = (key: string, values?: Record<string, string | number>) => string;

interface UseAiSettingsOptions {
  isLoggedIn: boolean;
  t: Translator;
}

export const DEFAULT_LLM_MODEL = 'qwen2.5:1.5b';
export const DEFAULT_EMBEDDING_MODEL = 'nomic-embed-text';
export const DEFAULT_SYSTEM_PROMPT =
  'Du bist Doctus, ein Enterprise-Wissensassistent. Du hilfst dabei, große, gewachsene Projektlandschaften zu verstehen — '
  + 'von COBOL-Beständen über Copybooks und JCL bis zu Dokumenten und angebundenen Wissensquellen (z. B. Confluence, Jira). '
  + 'Antworte präzise und begründet, stütze dich ausschließlich auf die dir bereitgestellten und indexierten Inhalte, '
  + 'und mache transparent, wenn dir Informationen fehlen oder unsicher sind.';

function readProfiles(t: Translator): LlmProfile[] {
  const savedProfiles = localStorage.getItem('doctus-llm-profiles');
  if (savedProfiles) {
    try {
      const parsed = JSON.parse(savedProfiles);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    } catch (error) {
      console.error('Failed to restore LLM profiles:', error);
    }
  }

  const legacyProvider = localStorage.getItem('doctus-llm-provider') || 'ollama';
  const legacyModel = localStorage.getItem('doctus-llm-model') || DEFAULT_LLM_MODEL;
  const legacyApiKey = localStorage.getItem('doctus-llm-api-key') || '';
  const legacyBaseUrl = localStorage.getItem('doctus-llm-base-url') || '';

  const profiles: LlmProfile[] = [{
    id: 'ollama-default',
    name: t('page.defaultLlmProfiles.localOllama'),
    provider: 'ollama',
    model: legacyProvider === 'ollama' ? legacyModel : DEFAULT_LLM_MODEL,
  }];

  if (legacyProvider !== 'ollama' || legacyModel !== DEFAULT_LLM_MODEL) {
    profiles.push({
      id: 'custom-legacy',
      name: legacyProvider === 'openai'
        ? t('page.defaultLlmProfiles.companyGpt')
        : t('page.defaultLlmProfiles.providerModel', { provider: legacyProvider.toUpperCase() }),
      provider: legacyProvider,
      model: legacyModel,
      apiKey: legacyApiKey,
      baseUrl: legacyBaseUrl,
    });
  }

  localStorage.setItem('doctus-llm-profiles', JSON.stringify(profiles));
  return profiles;
}

/**
 * Owns model discovery and the browser-persisted AI profile lifecycle.
 *
 * Chat and settings both need the active profile, while only the settings tab
 * edits profiles. Keeping the lifecycle here gives both consumers one source
 * of truth and keeps localStorage/API synchronization out of page.tsx.
 */
export function useAiSettings({ isLoggedIn, t }: UseAiSettingsOptions) {
  const [activeLlmModel, setActiveLlmModel] = useState(DEFAULT_LLM_MODEL);
  const [activeEmbeddingModel, setActiveEmbeddingModel] = useState(DEFAULT_EMBEDDING_MODEL);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [temperature, setTemperature] = useState(0.7);
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT);
  const [llmProfiles, setLlmProfiles] = useState<LlmProfile[]>([]);
  const [activeProfileId, setActiveProfileIdState] = useState('ollama-default');

  useEffect(() => {
    const profiles = readProfiles(t);
    // localStorage is an external client-side source. Restore it after the
    // server/default render so hydration stays deterministic.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLlmProfiles(profiles);

    const storedActiveId = localStorage.getItem('doctus-active-profile-id');
    const initialId = storedActiveId && profiles.some(profile => profile.id === storedActiveId)
      ? storedActiveId
      : profiles[0]?.id || 'ollama-default';

    setActiveProfileIdState(initialId);
    localStorage.setItem('doctus-active-profile-id', initialId);

    const activeProfile = profiles.find(profile => profile.id === initialId);
    if (activeProfile?.temperature !== undefined) setTemperature(activeProfile.temperature);
    if (activeProfile?.systemPrompt !== undefined) setSystemPrompt(activeProfile.systemPrompt);
  // Profile names are translated once during the initial browser restore. A
  // language switch must not recreate or overwrite the user's profiles.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isLoggedIn) return;

    api.getModelInfo()
      .then(res => {
        if (res.data.llm) setActiveLlmModel(res.data.llm);
        if (res.data.embedding) setActiveEmbeddingModel(res.data.embedding);
      })
      .catch(error => console.error('Failed to load model info:', error));

    api.getModels()
      .then(res => {
        if (res.data.models) setAvailableModels(res.data.models);
      })
      .catch(error => console.error('Failed to load available models:', error));
  }, [isLoggedIn]);

  const setActiveProfileId = useCallback((id: string) => {
    setActiveProfileIdState(id);
    localStorage.setItem('doctus-active-profile-id', id);

    const profile = llmProfiles.find(candidate => candidate.id === id);
    if (profile?.temperature !== undefined) setTemperature(profile.temperature);
    if (profile?.systemPrompt !== undefined) setSystemPrompt(profile.systemPrompt);
  }, [llmProfiles]);

  return {
    activeLlmModel,
    setActiveLlmModel,
    activeEmbeddingModel,
    setActiveEmbeddingModel,
    availableModels,
    temperature,
    setTemperature,
    systemPrompt,
    setSystemPrompt,
    llmProfiles,
    setLlmProfiles,
    activeProfileId,
    setActiveProfileId,
  };
}
