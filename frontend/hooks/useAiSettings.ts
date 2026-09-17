import { useCallback, useEffect, useState } from 'react';
import { api } from '@/app/services/api';

export interface LlmProfile {
  id: string;
  name: string;
  kind?: 'local' | 'remote' | 'cloud';
  provider: string;
  protocol?: 'ollama' | 'openai_chat' | 'openai_responses' | 'anthropic' | 'gemini';
  model: string;
  /** Local Ollama embedding model used for ingestion and retrieval. */
  embeddingModel?: string;
  baseUrl?: string;
  llmPath?: string;
  apiKeySet?: boolean;
  embeddingProvider?: string;
  embeddingBaseUrl?: string;
  embeddingPath?: string;
  embeddingApiKeySet?: boolean;
  embeddingDimension?: number;
  embeddingContextLength?: number;
  llmContextLength?: number;
  isSystem?: boolean;
  isActive?: boolean;
  temperature?: number;
  systemPrompt?: string;
}

type Translator = (key: string, values?: Record<string, string | number>) => string;

interface UseAiSettingsOptions {
  isLoggedIn: boolean;
  t: Translator;
}

export const DEFAULT_LLM_MODEL = 'qwen3:32b';
export const DEFAULT_EMBEDDING_MODEL = 'qwen3-embedding:4b';
export const DEFAULT_SYSTEM_PROMPT =
  'Du bist Doctus, ein Enterprise-Wissensassistent. Du hilfst dabei, große, gewachsene Projektlandschaften zu verstehen — '
  + 'von COBOL-Beständen über Copybooks und JCL bis zu Dokumenten und angebundenen Wissensquellen (z. B. Confluence, Jira). '
  + 'Antworte präzise und begründet, stütze dich ausschließlich auf die dir bereitgestellten und indexierten Inhalte, '
  + 'und mache transparent, wenn dir Informationen fehlen oder unsicher sind.';

export function profileFromApi(profile: Record<string, unknown>): LlmProfile {
  return {
    id: String(profile.id), name: profile.name as string,
    kind: profile.kind as LlmProfile['kind'], provider: profile.provider as string,
    protocol: profile.protocol as LlmProfile['protocol'], model: profile.llm_model as string,
    baseUrl: profile.llm_base_url as string | undefined, llmPath: profile.llm_path as string | undefined,
    apiKeySet: Boolean(profile.llm_api_key_set), embeddingProvider: profile.embedding_provider as string,
    embeddingModel: profile.embedding_model as string,
    embeddingBaseUrl: profile.embedding_base_url as string | undefined,
    embeddingPath: profile.embedding_path as string | undefined,
    embeddingApiKeySet: Boolean(profile.embedding_api_key_set),
    embeddingDimension: profile.embedding_dimension as number,
    embeddingContextLength: profile.embedding_context_length as number,
    llmContextLength: profile.llm_context_length as number,
    isSystem: Boolean(profile.is_system), isActive: Boolean(profile.is_active),
  };
}

function readProfiles(t: Translator): LlmProfile[] {
  const savedProfiles = localStorage.getItem('doctus-llm-profiles');
  if (savedProfiles) {
    try {
      const parsed = JSON.parse(savedProfiles);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed.map(profile => {
          const { apiKey: _discardedSecret, ...safeProfile } = profile;
          return ({
          ...safeProfile,
          model: !profile.model || profile.model === 'qwen2.5:1.5b'
            ? DEFAULT_LLM_MODEL
            : profile.model,
          // The deployment moved from bge-m3 to Qwen3 Embedding 4B. Replace
          // the old implicit profile value so new sources and retrieval use
          // the same vector space as the server default.
          embeddingModel: !profile.embeddingModel || profile.embeddingModel === 'bge-m3'
            ? DEFAULT_EMBEDDING_MODEL
            : profile.embeddingModel,
        });
        });
      }
    } catch (error) {
      console.error('Failed to restore LLM profiles:', error);
    }
  }

  const legacyProvider = localStorage.getItem('doctus-llm-provider') || 'ollama';
  const storedLegacyModel = localStorage.getItem('doctus-llm-model');
  const legacyModel = !storedLegacyModel || storedLegacyModel === 'qwen2.5:1.5b'
    ? DEFAULT_LLM_MODEL
    : storedLegacyModel;
  const legacyApiKey = localStorage.getItem('doctus-llm-api-key') || '';
  const legacyBaseUrl = localStorage.getItem('doctus-llm-base-url') || '';

  const profiles: LlmProfile[] = [{
    id: 'ollama-default',
    name: t('page.defaultLlmProfiles.localOllama'),
    provider: 'ollama',
    model: legacyProvider === 'ollama' ? legacyModel : DEFAULT_LLM_MODEL,
    embeddingModel: DEFAULT_EMBEDDING_MODEL,
  }];

  if (legacyProvider !== 'ollama' || legacyModel !== DEFAULT_LLM_MODEL) {
    profiles.push({
      id: 'custom-legacy',
      name: legacyProvider === 'openai'
        ? t('page.defaultLlmProfiles.companyGpt')
        : t('page.defaultLlmProfiles.providerModel', { provider: legacyProvider.toUpperCase() }),
      provider: legacyProvider,
      model: legacyModel,
          apiKeySet: Boolean(legacyApiKey),
      baseUrl: legacyBaseUrl,
      embeddingModel: DEFAULT_EMBEDDING_MODEL,
    });
  }

  localStorage.setItem('doctus-llm-profiles', JSON.stringify(profiles));
  localStorage.removeItem('doctus-llm-api-key');
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
  const [embeddingDimension, setEmbeddingDimension] = useState(1024);
  const [embeddingContextLength, setEmbeddingContextLength] = useState(8192);
  const [llmContextLength, setLlmContextLength] = useState(8192);

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

    api.getAiProfiles?.()
      .then(res => {
        const profiles: LlmProfile[] = (res.data.profiles || []).map(profileFromApi);
        if (!profiles.length) return;
        localStorage.removeItem('doctus-llm-profiles');
        const active = profiles.find(profile => profile.id === String(res.data.active_profile_id)) || profiles[0];
        setLlmProfiles(profiles);
        setActiveProfileIdState(active.id);
        localStorage.setItem('doctus-active-profile-id', String(active.id));
        setActiveLlmModel(active.model);
        setActiveEmbeddingModel(active.embeddingModel || DEFAULT_EMBEDDING_MODEL);
        setEmbeddingDimension(active.embeddingDimension || 1024);
        setEmbeddingContextLength(active.embeddingContextLength || 8192);
        setLlmContextLength(active.llmContextLength || 8192);
      })
      .catch(error => console.error('Failed to load persisted AI settings:', error));

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

  const activeProfileEmbeddingModel = llmProfiles.find(profile => profile.id === activeProfileId)?.embeddingModel;
  const effectiveActiveEmbeddingModel = activeProfileEmbeddingModel || activeEmbeddingModel || DEFAULT_EMBEDDING_MODEL;

  return {
    activeLlmModel,
    setActiveLlmModel,
    activeEmbeddingModel: effectiveActiveEmbeddingModel,
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
    embeddingDimension,
    setEmbeddingDimension,
    embeddingContextLength,
    setEmbeddingContextLength,
    llmContextLength,
    setLlmContextLength,
  };
}

function initialActiveProfileId(profiles: LlmProfile[]): string {
  const stored = localStorage.getItem('doctus-active-profile-id');
  return stored && profiles.some(profile => profile.id === stored) ? stored : profiles[0]?.id || 'ollama-default';
}
