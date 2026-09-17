"use client";

import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL, profileFromApi, type LlmProfile } from '@/hooks/useAiSettings';
import { useFeatures } from '@/lib/FeaturesContext';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Check, Edit, Plus, PlugZap, Trash2 } from 'lucide-react';
import React, { useState } from 'react';

type ProfileKind = 'local' | 'remote' | 'cloud';
const inputClass = 'w-full h-9 border rounded-lg px-3 text-xs bg-transparent';

export const AiSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const features = useFeatures();
  const { theme, showToast, llmProfiles, setLlmProfiles, activeProfileId, setActiveProfileId } = useSettings();
  const [editing, setEditing] = useState<LlmProfile | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<ProfileKind>('local');
  const [provider, setProvider] = useState('ollama');
  const [protocol, setProtocol] = useState<LlmProfile['protocol']>('ollama');
  const [model, setModel] = useState(DEFAULT_LLM_MODEL);
  const [baseUrl, setBaseUrl] = useState('http://ollama:11434');
  const [llmPath, setLlmPath] = useState('/api/chat');
  const [apiKey, setApiKey] = useState('');
  const [embeddingProvider, setEmbeddingProvider] = useState('ollama');
  const [embeddingModel, setEmbeddingModel] = useState(DEFAULT_EMBEDDING_MODEL);
  const [embeddingBaseUrl, setEmbeddingBaseUrl] = useState('http://ollama:11434');
  const [embeddingPath, setEmbeddingPath] = useState('/api/embed');
  const [embeddingKey, setEmbeddingKey] = useState('');
  const [dimension, setDimension] = useState(1024);
  const [embeddingContext, setEmbeddingContext] = useState(8192);
  const [llmContext, setLlmContext] = useState(8192);

  const applyKind = (next: ProfileKind) => {
    setKind(next);
    if (next === 'local') {
      setProvider('ollama'); setProtocol('ollama'); setModel(DEFAULT_LLM_MODEL);
      setBaseUrl('http://ollama:11434'); setLlmPath('/api/chat');
      setEmbeddingProvider('ollama'); setEmbeddingBaseUrl('http://ollama:11434'); setEmbeddingPath('/api/embed');
    } else if (next === 'remote') {
      setProvider('ollama'); setProtocol('ollama'); setBaseUrl(''); setLlmPath('/api/chat');
      setEmbeddingProvider('ollama'); setEmbeddingBaseUrl(''); setEmbeddingPath('/api/embed');
    } else {
      setProvider('openai'); setProtocol('openai_responses'); setModel('gpt-6-astra');
      setBaseUrl('https://api.openai.com/v1'); setLlmPath('/responses');
      setEmbeddingProvider('ollama'); setEmbeddingBaseUrl('http://ollama:11434'); setEmbeddingPath('/api/embed');
    }
  };

  const applyCloudProvider = (next: string) => {
    setProvider(next);
    if (next === 'openai') {
      setProtocol('openai_responses'); setModel('gpt-6-astra');
      setBaseUrl('https://api.openai.com/v1'); setLlmPath('/responses');
    } else if (next === 'anthropic') {
      setProtocol('anthropic'); setModel('claude-sonnet-4-5');
      setBaseUrl('https://api.anthropic.com/v1'); setLlmPath('/messages');
    } else {
      setProtocol('gemini'); setModel('gemini-2.5-pro');
      setBaseUrl('https://generativelanguage.googleapis.com');
      setLlmPath('/v1beta/models/{model}:generateContent');
    }
  };

  const startAdd = () => {
    setEditing(null); setName(''); setApiKey(''); setEmbeddingKey('');
    setEmbeddingModel(DEFAULT_EMBEDDING_MODEL); setDimension(1024); setEmbeddingContext(8192); setLlmContext(8192);
    applyKind('local'); setShowForm(true);
  };

  const startEdit = (profile: LlmProfile) => {
    setEditing(profile); setName(profile.name); setKind(profile.kind || 'local'); setProvider(profile.provider);
    setProtocol(profile.protocol || 'ollama'); setModel(profile.model); setBaseUrl(profile.baseUrl || '');
    setLlmPath(profile.llmPath || ''); setApiKey(''); setEmbeddingProvider(profile.embeddingProvider || 'ollama');
    setEmbeddingModel(profile.embeddingModel || DEFAULT_EMBEDDING_MODEL);
    setEmbeddingBaseUrl(profile.embeddingBaseUrl || ''); setEmbeddingPath(profile.embeddingPath || '');
    setEmbeddingKey(''); setDimension(profile.embeddingDimension || 1024);
    setEmbeddingContext(profile.embeddingContextLength || 8192); setLlmContext(profile.llmContextLength || 8192);
    setShowForm(true);
  };

  const profilePayload = () => ({
    name: name.trim(), kind, provider, protocol, llm_model: model.trim(), llm_base_url: baseUrl.trim() || undefined,
    llm_path: llmPath.trim() || undefined, ...(apiKey ? { llm_api_key: apiKey } : {}),
    embedding_provider: embeddingProvider, embedding_model: embeddingModel.trim(),
    embedding_base_url: embeddingBaseUrl.trim() || undefined, embedding_path: embeddingPath.trim() || undefined,
    ...(embeddingKey ? { embedding_api_key: embeddingKey } : {}), embedding_dimension: dimension,
    embedding_context_length: embeddingContext, llm_context_length: llmContext,
  });

  const save = async () => {
    if (!name.trim() || !model.trim() || !embeddingModel.trim()) {
      showToast(t('settings.toast.profileNameRequired'), 'error'); return;
    }
    try {
      const response = editing
        ? await api.updateAiProfile(Number(editing.id), profilePayload())
        : await api.createAiProfile(profilePayload());
      const saved = profileFromApi(response.data as Record<string, unknown>);
      setLlmProfiles(editing ? llmProfiles.map(item => item.id === saved.id ? saved : item) : [...llmProfiles, saved]);
      setShowForm(false);
      showToast(editing ? t('settings.toast.profileUpdated') : t('settings.toast.profileCreated'), 'success');
    } catch (error) { showToast(t('settings.toast.aiParamsSaveFailed'), 'error', error); }
  };

  const activate = async (profile: LlmProfile) => {
    try {
      await api.activateAiProfile(Number(profile.id)); setActiveProfileId(profile.id);
      setLlmProfiles(llmProfiles.map(item => ({ ...item, isActive: item.id === profile.id })));
      showToast(t('settings.toast.aiParamsSaved'), 'success');
    } catch (error) { showToast(t('settings.toast.aiParamsSaveFailed'), 'error', error); }
  };

  const testProfile = async (profile: LlmProfile) => {
    try { await api.testAiProfile(Number(profile.id)); showToast(t('settings.profilesTab.testSuccess'), 'success'); }
    catch (error) { showToast(t('settings.profilesTab.testFailed'), 'error', error); }
  };

  const remove = async (profile: LlmProfile) => {
    try { await api.deleteAiProfile(Number(profile.id)); setLlmProfiles(llmProfiles.filter(item => item.id !== profile.id)); showToast(t('settings.toast.profileDeleted'), 'success'); }
    catch (error) { showToast(t('settings.toast.aiParamsSaveFailed'), 'error', error); }
  };

  return <div className="space-y-5">
    <div className="flex items-start justify-between gap-4">
      <div><h4 className="text-sm font-semibold">{t('settings.profilesTab.title')}</h4><p className="text-xs text-ds-zinc-500 mt-1">{t('settings.profilesTab.description')}</p></div>
      {!showForm && <Button size="sm" onClick={startAdd}><Plus className="w-4 h-4 mr-1" />{t('settings.profilesTab.addProfile')}</Button>}
    </div>
    {!showForm ? <div className="space-y-2">{llmProfiles.map(profile =>
      <div key={profile.id} className={cn('rounded-xl border p-4 flex items-center gap-2', profile.id === activeProfileId ? 'border-ds-indigo-500 bg-ds-indigo-500/5' : theme === 'dark' ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="flex-1 min-w-0"><div className="flex gap-2 items-center"><span className="font-semibold text-sm truncate">{profile.name}</span><span className="text-[10px] uppercase text-ds-zinc-500">{profile.kind}</span>{profile.id === activeProfileId && <Check className="w-4 h-4 text-ds-indigo-500" />}</div><div className="text-xs text-ds-zinc-500 mt-1 truncate">{profile.model}{profile.baseUrl ? ` · ${profile.baseUrl}` : ''}</div></div>
        <Button variant="ghost" size="sm" onClick={() => testProfile(profile)} title={t('settings.profilesTab.testProfile')}><PlugZap className="w-4 h-4" /></Button>
        {profile.id !== activeProfileId && <Button variant="outline" size="sm" onClick={() => activate(profile)}>{t('settings.profilesTab.activate')}</Button>}
        <Button variant="ghost" size="sm" onClick={() => startEdit(profile)}><Edit className="w-4 h-4" /></Button>
        <Button variant="ghost" size="sm" disabled={profile.isSystem || profile.id === activeProfileId} onClick={() => remove(profile)}><Trash2 className="w-4 h-4" /></Button>
      </div>)}</div> :
      <div className={cn('rounded-xl border p-4 space-y-4', theme === 'dark' ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="grid sm:grid-cols-2 gap-3"><Field label={t('settings.profilesTab.profileNameLabel')} value={name} set={setName} /><label className="text-xs">{t('settings.profilesTab.profileType')}<Select value={kind} onValueChange={value => applyKind(value as ProfileKind)} disabled={Boolean(editing?.isSystem)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="local">{t('settings.profilesTab.local')}</SelectItem><SelectItem value="remote">{t('settings.profilesTab.remote')}</SelectItem>{features.llm.allowCloudProviders && <SelectItem value="cloud">{t('settings.profilesTab.cloud')}</SelectItem>}</SelectContent></Select></label></div>
        {kind === 'remote' && <label className="text-xs">{t('settings.profilesTab.protocol')}<Select value={protocol} onValueChange={value => { const next = value as LlmProfile['protocol']; setProtocol(next); setProvider(next === 'ollama' ? 'ollama' : 'openai'); setLlmPath(next === 'ollama' ? '/api/chat' : '/chat/completions'); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="ollama">Ollama API</SelectItem><SelectItem value="openai_chat">OpenAI-kompatibel</SelectItem></SelectContent></Select></label>}
        {kind === 'cloud' && <label className="text-xs">{t('settings.profilesTab.providerLabel')}<Select value={provider} onValueChange={applyCloudProvider}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="openai">OpenAI</SelectItem><SelectItem value="anthropic">Anthropic</SelectItem><SelectItem value="gemini">Gemini</SelectItem></SelectContent></Select></label>}
        <div className="grid sm:grid-cols-2 gap-3"><Field label={t('settings.profilesTab.modelNameLabel')} value={model} set={setModel} />{kind !== 'local' && <Field label={t('settings.profilesTab.apiKeyLabel')} value={apiKey} set={setApiKey} secret placeholder={editing?.apiKeySet ? '••••••••' : ''} />}</div>
        {kind === 'remote' && <Field label={t('settings.profilesTab.baseUrlLabel')} value={baseUrl} set={setBaseUrl} placeholder="https://host:11434/subpath" />}
        <details className="text-xs"><summary className="cursor-pointer font-medium">{t('settings.profilesTab.advanced')}</summary><div className="grid sm:grid-cols-2 gap-3 mt-3"><Field label="Chat path" value={llmPath} set={setLlmPath} /><Field label="Embedding model" value={embeddingModel} set={setEmbeddingModel} />{kind === 'remote' && <><Field label="Embedding URL" value={embeddingBaseUrl} set={setEmbeddingBaseUrl} /><Field label="Embedding path" value={embeddingPath} set={setEmbeddingPath} /><Field label="Embedding API key" value={embeddingKey} set={setEmbeddingKey} secret placeholder={editing?.embeddingApiKeySet ? '••••••••' : ''} /></>}<NumberField label="Embedding dimension" value={dimension} set={setDimension} /><NumberField label="Embedding context" value={embeddingContext} set={setEmbeddingContext} /><NumberField label="LLM context" value={llmContext} set={setLlmContext} /></div></details>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setShowForm(false)}>{t('common.cancel')}</Button><Button onClick={save}>{t('settings.profilesTab.saveProfile')}</Button></div>
      </div>}
  </div>;
};

const Field = ({ label, value, set, secret = false, placeholder = '' }: { label: string; value: string; set: (value: string) => void; secret?: boolean; placeholder?: string }) => <label className="text-xs">{label}<input type={secret ? 'password' : 'text'} className={inputClass} value={value} placeholder={placeholder} onChange={event => set(event.target.value)} /></label>;
const NumberField = ({ label, value, set }: { label: string; value: number; set: (value: number) => void }) => <label className="text-xs">{label}<input type="number" min="1" className={inputClass} value={value} onChange={event => set(Number(event.target.value))} /></label>;
