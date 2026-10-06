"use client";

import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { activeCardClass, badgeClass, cardClass, dangerIconButtonClass, ghostIconButtonClass, helpTextClass, inputClass, primaryButtonClass, secondaryButtonClass, sectionTitleClass, settingsRoot, strongTextClass } from '@/components/settings/settingsStyles';
import { Button } from '@/components/ui/button';
import { Field, NumberField, SelectField, selectTriggerClass } from '@/components/settings/formFields';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL, embeddingProfileFromApi, profileFromApi, type EmbeddingProfile, type LlmProfile } from '@/hooks/useAiSettings';
import { useLlmDeployments, type LlmDeployment } from '@/hooks/useLlmDeployments';
import { useFeatures } from '@/lib/FeaturesContext';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { LocalDeploymentForm } from '@/components/settings/tabs/LocalDeploymentForm';
import { Check, ChevronRight, Edit, FileText, Play, Plus, PlugZap, Square, Trash2 } from 'lucide-react';
import React, { useState } from 'react';

type ProfileKind = 'local' | 'remote' | 'cloud';

export const AiSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const features = useFeatures();
  const { theme, showToast, llmProfiles, setLlmProfiles, activeProfileId, setActiveProfileId, embeddingProfiles, setEmbeddingProfiles, activeEmbeddingProfileId, setActiveEmbeddingProfileId } = useSettings();
  const { deployments, capabilities, error: deployerError, refresh: refreshDeployments } = useLlmDeployments(true);
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
    try { await api.deleteAiProfile(Number(profile.id)); setLlmProfiles(llmProfiles.filter(item => item.id !== profile.id)); refreshDeployments(); showToast(t('settings.toast.profileDeleted'), 'success'); }
    catch (error) { showToast(t('settings.toast.aiParamsSaveFailed'), 'error', error); }
  };

  const kindSelect = (
            <SelectField label={t('settings.profilesTab.profileType')}>
              <Select value={kind} onValueChange={value => applyKind(value as ProfileKind)} disabled={Boolean(editing?.isSystem || editing?.deploymentName)}>
                <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="local">{t('settings.profilesTab.local')}</SelectItem><SelectItem value="remote">{t('settings.profilesTab.remote')}</SelectItem>{features.llm.allowCloudProviders && <SelectItem value="cloud">{t('settings.profilesTab.cloud')}</SelectItem>}</SelectContent>
              </Select>
            </SelectField>
  );
  const isNewLocal = showForm && !editing && kind === 'local';

  const onDeploymentCreated = ({ profile }: { profile: Record<string, unknown> }) => {
    const saved = profileFromApi(profile);
    const first = llmProfiles.length === 0;
    setLlmProfiles([...llmProfiles, first ? { ...saved, isActive: true } : saved]);
    if (first) setActiveProfileId(saved.id);
    setShowForm(false);
    refreshDeployments();
    showToast(t('settings.deployments.created'), 'success');
  };

  return <div className={settingsRoot}>
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h4 className={sectionTitleClass(theme)}>{t('settings.profilesTab.title')}</h4>
          <p className={helpTextClass}>{t('settings.profilesTab.description')}</p>
        </div>
        {!showForm && <Button size="sm" onClick={startAdd} className={primaryButtonClass}><Plus className="w-3.5 h-3.5" />{t('settings.profilesTab.addProfile')}</Button>}
      </div>
      {!showForm ? <div className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">{llmProfiles.map(profile =>
        <div key={profile.id} className={cn(profile.id === activeProfileId ? activeCardClass(theme) : cardClass(theme), 'p-3.5 flex flex-wrap items-center gap-2')}>
          <div className="flex-1 min-w-0">
            <div className="flex gap-2 items-center">
              <span className={cn('text-xs truncate', strongTextClass(theme))}>{profile.name}</span>
              <span className={badgeClass('neutral')}>{profile.kind}</span>
              {ENGINE_LABEL[profile.provider] && <span className={badgeClass('accent')}>{ENGINE_LABEL[profile.provider]}</span>}
              {profile.deploymentName && <DeploymentBadge deployment={deployments.find(item => item.name === profile.deploymentName)} />}
              {profile.id === activeProfileId && <Check className="w-3.5 h-3.5 text-ds-indigo-500" />}
            </div>
            <div className="font-mono text-[0.6875rem] text-ds-zinc-500 mt-1 truncate">{profile.model}{profile.baseUrl ? ` · ${profile.baseUrl}` : ''}</div>
          </div>
          {profile.deploymentName && <DeploymentControls name={profile.deploymentName} deployment={deployments.find(item => item.name === profile.deploymentName)} showToast={showToast} onChanged={refreshDeployments} />}
          <Button variant="ghost" size="icon" onClick={() => testProfile(profile)} title={t('settings.profilesTab.testProfile')} className={ghostIconButtonClass}><PlugZap className="w-3.5 h-3.5" /></Button>
          {profile.id !== activeProfileId && <Button variant="outline" size="sm" onClick={() => activate(profile)} className={secondaryButtonClass(theme)}>{t('settings.profilesTab.activate')}</Button>}
          <Button variant="ghost" size="icon" onClick={() => startEdit(profile)} className={ghostIconButtonClass}><Edit className="w-3.5 h-3.5" /></Button>
          <Button variant="ghost" size="icon" disabled={profile.isSystem || profile.id === activeProfileId} onClick={() => remove(profile)} className={dangerIconButtonClass}><Trash2 className="w-3.5 h-3.5" /></Button>
        </div>)}{llmProfiles.length === 0 && <p className={cn(cardClass(theme), 'border-dashed p-4 text-center text-xs text-ds-zinc-500')}>{t('settings.deployments.emptyLlm')}</p>}</div> :
        isNewLocal ? <div className="space-y-3">
          <div className="max-w-xs">{kindSelect}</div>
          <LocalDeploymentForm theme={theme} role="chat" capabilities={capabilities} existing={deployments} deployerError={deployerError}
            onCreated={onDeploymentCreated} onCancel={() => setShowForm(false)} showToast={showToast} />
        </div> :
        <div className={cn(cardClass(theme), 'p-4 space-y-4')}>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label={t('settings.profilesTab.profileNameLabel')} value={name} set={setName} />
            {kindSelect}
          </div>
          {kind === 'remote' && <SelectField label={t('settings.profilesTab.protocol')}>
            <Select value={provider === 'vllm' || provider === 'llamacpp' ? provider : protocol} onValueChange={value => {
              if (value === 'vllm' || value === 'llamacpp') {
                setProvider(value); setProtocol('openai_chat'); setLlmPath('/chat/completions');
                setBaseUrl(current => current.trim() || (value === 'vllm' ? 'http://vllm:8000/v1' : 'http://llamacpp:8080/v1'));
              } else {
                const next = value as LlmProfile['protocol']; setProtocol(next); setProvider(next === 'ollama' ? 'ollama' : 'openai'); setLlmPath(next === 'ollama' ? '/api/chat' : '/chat/completions');
              }
            }}>
              <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="ollama">{t('settings.profilesTab.protocolOllama')}</SelectItem><SelectItem value="openai_chat">{t('settings.profilesTab.protocolOpenai')}</SelectItem><SelectItem value="vllm">{t('settings.profilesTab.protocolVllm')}</SelectItem><SelectItem value="llamacpp">{t('settings.profilesTab.protocolLlamacpp')}</SelectItem></SelectContent>
            </Select>
          </SelectField>}
          {kind === 'remote' && provider === 'vllm' && <p className={helpTextClass}>{t('settings.profilesTab.vllmHint')}</p>}
          {kind === 'remote' && provider === 'llamacpp' && <p className={helpTextClass}>{t('settings.profilesTab.llamacppHint')}</p>}
          {kind === 'cloud' && <SelectField label={t('settings.profilesTab.providerLabel')}>
            <Select value={provider} onValueChange={applyCloudProvider}>
              <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="openai">OpenAI</SelectItem><SelectItem value="anthropic">Anthropic</SelectItem><SelectItem value="gemini">Gemini</SelectItem></SelectContent>
            </Select>
          </SelectField>}
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label={t('settings.profilesTab.modelNameLabel')} value={model} set={setModel} />
            {kind !== 'local' && <Field label={t('settings.profilesTab.apiKeyLabel')} value={apiKey} set={setApiKey} secret placeholder={editing?.apiKeySet ? '••••••••' : ''} />}
          </div>
          {kind === 'remote' && <Field label={t('settings.profilesTab.baseUrlLabel')} value={baseUrl} set={setBaseUrl} placeholder="https://host:11434/subpath" />}
          <details className="group">
            <summary className={cn(sectionTitleClass(theme), 'cursor-pointer list-none flex items-center gap-1.5 [&::-webkit-details-marker]:hidden')}>
              <ChevronRight className="w-3.5 h-3.5 transition-transform group-open:rotate-90" />{t('settings.profilesTab.advanced')}
            </summary>
            <div className="grid sm:grid-cols-2 gap-3 mt-3">
              <Field label={t('settings.profilesTab.chatPathLabel')} value={llmPath} set={setLlmPath} />
              <Field label={t('settings.profilesTab.embeddingModelShortLabel')} value={embeddingModel} set={setEmbeddingModel} />
              {kind === 'remote' && <>
                <Field label={t('settings.profilesTab.embeddingUrlLabel')} value={embeddingBaseUrl} set={setEmbeddingBaseUrl} />
                <Field label={t('settings.profilesTab.embeddingPathLabel')} value={embeddingPath} set={setEmbeddingPath} />
                <Field label={t('settings.profilesTab.embeddingApiKeyLabel')} value={embeddingKey} set={setEmbeddingKey} secret placeholder={editing?.embeddingApiKeySet ? '••••••••' : ''} />
              </>}
              <NumberField label={t('settings.profilesTab.embeddingDimensionLabel')} value={dimension} set={setDimension} />
              <NumberField label={t('settings.profilesTab.embeddingContextLabel')} value={embeddingContext} set={setEmbeddingContext} />
              <NumberField label={t('settings.profilesTab.llmContextLabel')} value={llmContext} set={setLlmContext} />
            </div>
          </details>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowForm(false)} className={cn(secondaryButtonClass(theme), 'h-9 text-xs')}>{t('common.cancel')}</Button>
            <Button onClick={save} className={primaryButtonClass}>{t('settings.profilesTab.saveProfile')}</Button>
          </div>
        </div>}
    </section>
    <EmbeddingProfilesPanel
      theme={theme}
      showToast={showToast}
      profiles={embeddingProfiles}
      setProfiles={setEmbeddingProfiles}
      activeProfileId={activeEmbeddingProfileId}
      setActiveProfileId={setActiveEmbeddingProfileId}
      deployments={deployments}
      capabilities={capabilities}
      deployerError={deployerError}
      refreshDeployments={refreshDeployments}
    />
  </div>;
};

function EmbeddingProfilesPanel({
  theme, showToast, profiles = [], setProfiles, activeProfileId, setActiveProfileId,
  deployments, capabilities, deployerError, refreshDeployments,
}: {
  deployments: LlmDeployment[];
  capabilities: { gpu: boolean };
  deployerError: string | null;
  refreshDeployments: () => void;
  theme: string;
  showToast: (message: string, kind?: 'success' | 'error', error?: unknown) => void;
  profiles?: EmbeddingProfile[];
  setProfiles: React.Dispatch<React.SetStateAction<EmbeddingProfile[]>>;
  activeProfileId: string;
  setActiveProfileId: (id: string) => void;
}) {
  const { t } = useLanguage();
  const [editing, setEditing] = useState<EmbeddingProfile | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [provider, setProvider] = useState<'ollama' | 'openai'>('openai');
  const [model, setModel] = useState(DEFAULT_EMBEDDING_MODEL);
  const [baseUrl, setBaseUrl] = useState('');
  const [path, setPath] = useState('/embeddings');
  const [apiKey, setApiKey] = useState('');
  const [dimension, setDimension] = useState(1024);
  const [contextLength, setContextLength] = useState(8192);
  // Neues Profil: lokales Deployment (Standard) oder externer Endpunkt.
  const [mode, setMode] = useState<'local' | 'external'>('local');

  const reset = () => {
    setEditing(null); setName(''); setProvider('openai'); setModel(DEFAULT_EMBEDDING_MODEL);
    setBaseUrl(''); setPath('/embeddings'); setApiKey(''); setDimension(1024); setContextLength(8192); setMode('local');
  };
  const edit = (profile: EmbeddingProfile) => {
    setEditing(profile); setName(profile.name); setProvider(profile.provider === 'ollama' ? 'ollama' : 'openai');
    setModel(profile.model); setBaseUrl(profile.baseUrl); setPath(profile.path); setApiKey('');
    setDimension(profile.dimension); setContextLength(profile.contextLength); setMode('external'); setShowForm(true);
  };
  const save = async () => {
    if (!name.trim() || !model.trim() || !baseUrl.trim()) return;
    const payload = { name: name.trim(), provider, model: model.trim(), base_url: baseUrl.trim(), path: path.trim(), ...(apiKey ? { api_key: apiKey } : {}), dimension, context_length: contextLength };
    try {
      const response = editing
        ? await api.updateEmbeddingProfile(Number(editing.id), payload)
        : await api.createEmbeddingProfile(payload);
      const saved = embeddingProfileFromApi(response.data as Record<string, unknown>);
      setProfiles(editing ? profiles.map(item => item.id === saved.id ? saved : item) : [...profiles, saved]);
      setShowForm(false); reset(); showToast(t('settings.embeddingTab.saved'), 'success');
    } catch (error) { showToast(t('settings.embeddingTab.saveFailed'), 'error', error); }
  };
  const onDeploymentCreated = ({ profile }: { profile: Record<string, unknown> }) => {
    const saved = embeddingProfileFromApi(profile);
    const first = profiles.length === 0;
    setProfiles([...profiles, first ? { ...saved, isActive: true } : saved]);
    if (first) setActiveProfileId(saved.id);
    setShowForm(false); reset(); refreshDeployments();
    showToast(t('settings.deployments.created'), 'success');
  };
  const removeProfile = async (profile: EmbeddingProfile) => {
    try { await api.deleteEmbeddingProfile(Number(profile.id)); setProfiles(profiles.filter(item => item.id !== profile.id)); refreshDeployments(); }
    catch (error) { showToast(t('settings.embeddingTab.saveFailed'), 'error', error); }
  };
  const activate = async (profile: EmbeddingProfile) => {
    try {
      await api.activateEmbeddingProfile(Number(profile.id));
      setActiveProfileId(profile.id);
      setProfiles(profiles.map(item => ({ ...item, isActive: item.id === profile.id })));
      showToast(t('settings.embeddingTab.activated'), 'success');
    } catch (error) { showToast(t('settings.embeddingTab.activateFailed'), 'error', error); }
  };
  const test = async (profile: EmbeddingProfile) => {
    try { await api.testEmbeddingProfile(Number(profile.id)); showToast(t('settings.embeddingTab.testSuccess'), 'success'); }
    catch (error) { showToast(t('settings.embeddingTab.testFailed'), 'error', error); }
  };

  return <section className="space-y-4">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <h4 className={sectionTitleClass(theme)}>{t('settings.embeddingTab.title')}</h4>
        <p className={helpTextClass}>{t('settings.embeddingTab.description')}</p>
      </div>
      {!showForm && <Button size="sm" onClick={() => { reset(); setShowForm(true); }} className={primaryButtonClass}><Plus className="w-3.5 h-3.5" />{t('settings.embeddingTab.addProfile')}</Button>}
    </div>
    {!showForm ? <div className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">{profiles.map(profile => <div key={profile.id} className={cn(profile.id === activeProfileId ? activeCardClass(theme) : cardClass(theme), 'p-3.5 flex flex-wrap items-center gap-2')}>
      <div className="flex-1 min-w-0">
        <div className="flex gap-2 items-center"><span className={cn('text-xs truncate', strongTextClass(theme))}>{profile.name}</span>{profile.id === activeProfileId && <Check className="w-3.5 h-3.5 text-ds-indigo-500" />}{profile.deploymentName && <DeploymentBadge deployment={deployments.find(item => item.name === profile.deploymentName)} />}</div>
        <div className="font-mono text-[0.6875rem] text-ds-zinc-500 mt-1 truncate">{profile.model} · {profile.provider} · {profile.dimension}D</div>
      </div>
      {profile.deploymentName && <DeploymentControls name={profile.deploymentName} deployment={deployments.find(item => item.name === profile.deploymentName)} showToast={showToast} onChanged={refreshDeployments} />}
      <Button variant="ghost" size="icon" onClick={() => test(profile)} title={t('settings.embeddingTab.testTitle')} aria-label={t('settings.embeddingTab.testTitle')} className={ghostIconButtonClass}><PlugZap className="w-3.5 h-3.5" /></Button>
      {profile.id !== activeProfileId && <Button variant="outline" size="sm" onClick={() => activate(profile)} className={secondaryButtonClass(theme)}>{t('settings.embeddingTab.activate')}</Button>}
      <Button variant="ghost" size="icon" onClick={() => edit(profile)} title={t('settings.embeddingTab.editTitle')} aria-label={t('settings.embeddingTab.editTitle')} className={ghostIconButtonClass}><Edit className="w-3.5 h-3.5" /></Button>
      <Button variant="ghost" size="icon" disabled={profile.isSystem || profile.id === activeProfileId} onClick={() => removeProfile(profile)} title={t('settings.embeddingTab.deleteTitle')} aria-label={t('settings.embeddingTab.deleteTitle')} className={dangerIconButtonClass}><Trash2 className="w-3.5 h-3.5" /></Button>
    </div>)}{profiles.length === 0 && <p className={cn(cardClass(theme), 'border-dashed p-4 text-center text-xs text-ds-zinc-500')}>{t('settings.deployments.emptyEmbedding')}</p>}</div> : !editing && mode === 'local' ? <div className="space-y-3">
      <ModeSwitch theme={theme} mode={mode} setMode={setMode} />
      <LocalDeploymentForm theme={theme} role="embedding" capabilities={capabilities} existing={deployments} deployerError={deployerError}
        onCreated={onDeploymentCreated} onCancel={() => { setShowForm(false); reset(); }} showToast={showToast} />
    </div> : <div className={cn(cardClass(theme), 'p-4 grid sm:grid-cols-2 gap-3')}>
      {!editing && <div className="sm:col-span-2"><ModeSwitch theme={theme} mode={mode} setMode={setMode} /></div>}
      <Field label={t('settings.embeddingTab.nameLabel')} value={name} set={setName} />
      <SelectField label={t('settings.embeddingTab.providerLabel')}>
        <Select value={provider} onValueChange={value => { const next = value as 'ollama' | 'openai'; setProvider(next); setPath(next === 'openai' ? '/embeddings' : '/api/embed'); }}>
          <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="openai">{t('settings.embeddingTab.providerOpenai')}</SelectItem><SelectItem value="ollama">{t('settings.embeddingTab.providerOllama')}</SelectItem></SelectContent>
        </Select>
      </SelectField>
      <Field label={t('settings.embeddingTab.modelLabel')} value={model} set={setModel} /><Field label={t('settings.embeddingTab.baseUrlLabel')} value={baseUrl} set={setBaseUrl} placeholder="https://host.example/v1" />
      <Field label={t('settings.embeddingTab.pathLabel')} value={path} set={setPath} /><Field label={t('settings.embeddingTab.apiKeyLabel')} value={apiKey} set={setApiKey} secret placeholder={editing?.apiKeySet ? '••••••••' : ''} />
      <NumberField label={t('settings.embeddingTab.dimensionLabel')} value={dimension} set={setDimension} /><NumberField label={t('settings.embeddingTab.contextLengthLabel')} value={contextLength} set={setContextLength} />
      <div className="sm:col-span-2 flex justify-end gap-2">
        <Button variant="outline" onClick={() => { setShowForm(false); reset(); }} className={cn(secondaryButtonClass(theme), 'h-9 text-xs')}>{t('common.cancel')}</Button>
        <Button onClick={save} className={primaryButtonClass}>{t('common.save')}</Button>
      </div>
    </div>}
  </section>;
}

const ENGINE_LABEL: Record<string, string> = { ollama: 'Ollama', vllm: 'vLLM', llamacpp: 'llama.cpp' };

function ModeSwitch({ theme, mode, setMode }: { theme: string; mode: 'local' | 'external'; setMode: (mode: 'local' | 'external') => void }) {
  const { t } = useLanguage();
  return <div role="group" className={cn('inline-flex rounded-lg border p-0.5', theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-900' : 'border-ds-zinc-200 bg-ds-white')}>
    {(['local', 'external'] as const).map(value => <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)}
      className={cn('h-7 rounded-md px-3 text-[0.6875rem] font-semibold transition-colors', mode === value ? 'bg-ds-indigo-650 text-ds-white' : 'text-ds-zinc-500 hover:text-ds-zinc-300')}>
      {t(`settings.deployments.mode.${value}`)}
    </button>)}
  </div>;
}

function DeploymentBadge({ deployment }: { deployment?: LlmDeployment }) {
  const { t } = useLanguage();
  if (!deployment) return <span className={badgeClass('warning')}>{t('settings.deployments.status.missing')}</span>;
  const tone = deployment.status === 'ready' ? 'success' : deployment.status === 'failed' ? 'danger' : deployment.status === 'stopped' ? 'neutral' : 'accent';
  return <span className={badgeClass(tone)} title={deployment.detail}>{t(`settings.deployments.status.${deployment.status}`)}</span>;
}

/** Start/Stopp und Log eines lokalen Deployments direkt an der Profilzeile. */
function DeploymentControls({ name, deployment, showToast, onChanged }: {
  name: string; deployment?: LlmDeployment;
  showToast: (message: string, kind?: 'success' | 'error', error?: unknown) => void; onChanged: () => void;
}) {
  const { t } = useLanguage();
  const [logs, setLogs] = useState<string | null>(null);
  const running = deployment != null && deployment.status !== 'stopped';
  const toggle = async () => {
    try { await api.controlLlmDeployment(name, running ? 'stop' : 'start'); onChanged(); }
    catch (error) { showToast(t('settings.deployments.controlFailed'), 'error', error); }
  };
  const showLogs = async () => {
    if (logs !== null) { setLogs(null); return; }
    try { const response = await api.getLlmDeploymentLogs(name, 200); setLogs((response.data as { logs: string }).logs || ' '); }
    catch (error) { showToast(t('settings.deployments.logsFailed'), 'error', error); }
  };
  return <>
    {deployment && <Button variant="ghost" size="icon" onClick={toggle} title={t(running ? 'settings.deployments.stop' : 'settings.deployments.start')} aria-label={t(running ? 'settings.deployments.stop' : 'settings.deployments.start')} className={ghostIconButtonClass}>{running ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}</Button>}
    {deployment && <Button variant="ghost" size="icon" onClick={showLogs} title={t('settings.deployments.logs')} aria-label={t('settings.deployments.logs')} aria-pressed={logs !== null} className={ghostIconButtonClass}><FileText className="w-3.5 h-3.5" /></Button>}
    {logs !== null && <pre data-testid="deployment-logs" className="basis-full max-h-56 overflow-auto rounded-lg border border-ds-zinc-800 bg-ds-zinc-950 p-3 font-mono text-[0.625rem] leading-relaxed text-ds-zinc-300 whitespace-pre-wrap break-words">{logs}</pre>}
  </>;
}
