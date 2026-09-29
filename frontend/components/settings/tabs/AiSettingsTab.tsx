"use client";

import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { activeCardClass, badgeClass, cardClass, dangerIconButtonClass, ghostIconButtonClass, helpTextClass, inputClass, primaryButtonClass, secondaryButtonClass, sectionTitleClass, settingsRoot, strongTextClass } from '@/components/settings/settingsStyles';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL, embeddingProfileFromApi, profileFromApi, type EmbeddingProfile, type LlmProfile } from '@/hooks/useAiSettings';
import { useFeatures } from '@/lib/FeaturesContext';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Check, ChevronRight, Edit, Plus, PlugZap, Trash2 } from 'lucide-react';
import React, { useState } from 'react';

type ProfileKind = 'local' | 'remote' | 'cloud';

export const AiSettingsTab: React.FC = () => {
  const { t } = useLanguage();
  const features = useFeatures();
  const { theme, showToast, llmProfiles, setLlmProfiles, activeProfileId, setActiveProfileId, embeddingProfiles, setEmbeddingProfiles, activeEmbeddingProfileId, setActiveEmbeddingProfileId } = useSettings();
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

  return <div className={settingsRoot}>
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h4 className={sectionTitleClass(theme)}>{t('settings.profilesTab.title')}</h4>
          <p className={helpTextClass}>{t('settings.profilesTab.description')}</p>
        </div>
        {!showForm && <Button size="sm" onClick={startAdd} className={primaryButtonClass}><Plus className="w-3.5 h-3.5" />{t('settings.profilesTab.addProfile')}</Button>}
      </div>
      {!showForm ? <div className="space-y-2">{llmProfiles.map(profile =>
        <div key={profile.id} className={cn(profile.id === activeProfileId ? activeCardClass(theme) : cardClass(theme), 'p-3.5 flex items-center gap-2')}>
          <div className="flex-1 min-w-0">
            <div className="flex gap-2 items-center">
              <span className={cn('text-xs truncate', strongTextClass(theme))}>{profile.name}</span>
              <span className={badgeClass('neutral')}>{profile.kind}</span>
              {profile.provider === 'vllm' && <span className={badgeClass('accent')}>vLLM</span>}
              {profile.id === activeProfileId && <Check className="w-3.5 h-3.5 text-ds-indigo-500" />}
            </div>
            <div className="font-mono text-[0.6875rem] text-ds-zinc-500 mt-1 truncate">{profile.model}{profile.baseUrl ? ` · ${profile.baseUrl}` : ''}</div>
          </div>
          <Button variant="ghost" size="icon" onClick={() => testProfile(profile)} title={t('settings.profilesTab.testProfile')} className={ghostIconButtonClass}><PlugZap className="w-3.5 h-3.5" /></Button>
          {profile.id !== activeProfileId && <Button variant="outline" size="sm" onClick={() => activate(profile)} className={secondaryButtonClass(theme)}>{t('settings.profilesTab.activate')}</Button>}
          <Button variant="ghost" size="icon" onClick={() => startEdit(profile)} className={ghostIconButtonClass}><Edit className="w-3.5 h-3.5" /></Button>
          <Button variant="ghost" size="icon" disabled={profile.isSystem || profile.id === activeProfileId} onClick={() => remove(profile)} className={dangerIconButtonClass}><Trash2 className="w-3.5 h-3.5" /></Button>
        </div>)}</div> :
        <div className={cn(cardClass(theme), 'p-4 space-y-4')}>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label={t('settings.profilesTab.profileNameLabel')} value={name} set={setName} />
            <SelectField label={t('settings.profilesTab.profileType')}>
              <Select value={kind} onValueChange={value => applyKind(value as ProfileKind)} disabled={Boolean(editing?.isSystem)}>
                <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="local">{t('settings.profilesTab.local')}</SelectItem><SelectItem value="remote">{t('settings.profilesTab.remote')}</SelectItem>{features.llm.allowCloudProviders && <SelectItem value="cloud">{t('settings.profilesTab.cloud')}</SelectItem>}</SelectContent>
              </Select>
            </SelectField>
          </div>
          {kind === 'remote' && <SelectField label={t('settings.profilesTab.protocol')}>
            <Select value={provider === 'vllm' ? 'vllm' : protocol} onValueChange={value => { if (value === 'vllm') { setProvider('vllm'); setProtocol('openai_chat'); setBaseUrl(current => current.trim() || 'http://vllm:8000/v1'); setLlmPath('/chat/completions'); } else { const next = value as LlmProfile['protocol']; setProtocol(next); setProvider(next === 'ollama' ? 'ollama' : 'openai'); setLlmPath(next === 'ollama' ? '/api/chat' : '/chat/completions'); } }}>
              <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="ollama">Ollama API</SelectItem><SelectItem value="openai_chat">OpenAI-kompatibel</SelectItem><SelectItem value="vllm">vLLM (OpenAI API)</SelectItem></SelectContent>
            </Select>
          </SelectField>}
          {kind === 'remote' && provider === 'vllm' && <p className={helpTextClass}>{t('settings.profilesTab.vllmHint')}</p>}
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
              <Field label="Chat path" value={llmPath} set={setLlmPath} />
              <Field label="Embedding model" value={embeddingModel} set={setEmbeddingModel} />
              {kind === 'remote' && <>
                <Field label="Embedding URL" value={embeddingBaseUrl} set={setEmbeddingBaseUrl} />
                <Field label="Embedding path" value={embeddingPath} set={setEmbeddingPath} />
                <Field label="Embedding API key" value={embeddingKey} set={setEmbeddingKey} secret placeholder={editing?.embeddingApiKeySet ? '••••••••' : ''} />
              </>}
              <NumberField label="Embedding dimension" value={dimension} set={setDimension} />
              <NumberField label="Embedding context" value={embeddingContext} set={setEmbeddingContext} />
              <NumberField label="LLM context" value={llmContext} set={setLlmContext} />
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
    />
  </div>;
};

function EmbeddingProfilesPanel({
  theme, showToast, profiles = [], setProfiles, activeProfileId, setActiveProfileId,
}: {
  theme: string;
  showToast: (message: string, kind?: 'success' | 'error', error?: unknown) => void;
  profiles?: EmbeddingProfile[];
  setProfiles: React.Dispatch<React.SetStateAction<EmbeddingProfile[]>>;
  activeProfileId: string;
  setActiveProfileId: (id: string) => void;
}) {
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

  const reset = () => {
    setEditing(null); setName(''); setProvider('openai'); setModel(DEFAULT_EMBEDDING_MODEL);
    setBaseUrl(''); setPath('/embeddings'); setApiKey(''); setDimension(1024); setContextLength(8192);
  };
  const edit = (profile: EmbeddingProfile) => {
    setEditing(profile); setName(profile.name); setProvider(profile.provider === 'ollama' ? 'ollama' : 'openai');
    setModel(profile.model); setBaseUrl(profile.baseUrl); setPath(profile.path); setApiKey('');
    setDimension(profile.dimension); setContextLength(profile.contextLength); setShowForm(true);
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
      setShowForm(false); reset(); showToast('Embedding-Profil gespeichert', 'success');
    } catch (error) { showToast('Embedding-Profil konnte nicht gespeichert werden', 'error', error); }
  };
  const activate = async (profile: EmbeddingProfile) => {
    try {
      await api.activateEmbeddingProfile(Number(profile.id));
      setActiveProfileId(profile.id);
      setProfiles(profiles.map(item => ({ ...item, isActive: item.id === profile.id })));
      showToast('Embedding-Profil aktiviert', 'success');
    } catch (error) { showToast('Embedding-Profil konnte nicht aktiviert werden', 'error', error); }
  };
  const test = async (profile: EmbeddingProfile) => {
    try { await api.testEmbeddingProfile(Number(profile.id)); showToast('Embedding-Endpunkt erreichbar', 'success'); }
    catch (error) { showToast('Embedding-Endpunkt nicht erreichbar oder Dimension falsch', 'error', error); }
  };

  return <section className="space-y-4">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <h4 className={sectionTitleClass(theme)}>Embedding-Profile</h4>
        <p className={helpTextClass}>Unabhängig vom LLM. Das aktive Profil wird für Import und semantische Suche verwendet.</p>
      </div>
      {!showForm && <Button size="sm" onClick={() => { reset(); setShowForm(true); }} className={primaryButtonClass}><Plus className="w-3.5 h-3.5" />Embedding-Profil hinzufügen</Button>}
    </div>
    {!showForm ? <div className="space-y-2">{profiles.map(profile => <div key={profile.id} className={cn(profile.id === activeProfileId ? activeCardClass(theme) : cardClass(theme), 'p-3.5 flex items-center gap-2')}>
      <div className="flex-1 min-w-0">
        <div className="flex gap-2 items-center"><span className={cn('text-xs truncate', strongTextClass(theme))}>{profile.name}</span>{profile.id === activeProfileId && <Check className="w-3.5 h-3.5 text-ds-indigo-500" />}</div>
        <div className="font-mono text-[0.6875rem] text-ds-zinc-500 mt-1 truncate">{profile.model} · {profile.provider} · {profile.dimension}D</div>
      </div>
      <Button variant="ghost" size="icon" onClick={() => test(profile)} className={ghostIconButtonClass}><PlugZap className="w-3.5 h-3.5" /></Button>
      {profile.id !== activeProfileId && <Button variant="outline" size="sm" onClick={() => activate(profile)} className={secondaryButtonClass(theme)}>Aktivieren</Button>}
      <Button variant="ghost" size="icon" onClick={() => edit(profile)} className={ghostIconButtonClass}><Edit className="w-3.5 h-3.5" /></Button>
      <Button variant="ghost" size="icon" disabled={profile.isSystem || profile.id === activeProfileId} onClick={async () => { await api.deleteEmbeddingProfile(Number(profile.id)); setProfiles(profiles.filter(item => item.id !== profile.id)); }} className={dangerIconButtonClass}><Trash2 className="w-3.5 h-3.5" /></Button>
    </div>)}</div> : <div className={cn(cardClass(theme), 'p-4 grid sm:grid-cols-2 gap-3')}>
      <Field label="Name" value={name} set={setName} />
      <SelectField label="Provider">
        <Select value={provider} onValueChange={value => { const next = value as 'ollama' | 'openai'; setProvider(next); setPath(next === 'openai' ? '/embeddings' : '/api/embed'); }}>
          <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="openai">OpenAI-kompatibel</SelectItem><SelectItem value="ollama">Ollama API</SelectItem></SelectContent>
        </Select>
      </SelectField>
      <Field label="Modell" value={model} set={setModel} /><Field label="Base-URL" value={baseUrl} set={setBaseUrl} placeholder="https://host.example/v1" />
      <Field label="Embedding-Pfad" value={path} set={setPath} /><Field label="API-Key" value={apiKey} set={setApiKey} secret placeholder={editing?.apiKeySet ? '••••••••' : ''} />
      <NumberField label="Dimension" value={dimension} set={setDimension} /><NumberField label="Context-Länge" value={contextLength} set={setContextLength} />
      <div className="sm:col-span-2 flex justify-end gap-2">
        <Button variant="outline" onClick={() => { setShowForm(false); reset(); }} className={cn(secondaryButtonClass(theme), 'h-9 text-xs')}>Abbrechen</Button>
        <Button onClick={save} className={primaryButtonClass}>Speichern</Button>
      </div>
    </div>}
  </section>;
}

const selectTriggerClass = 'h-9 text-xs font-semibold';

const FieldLabel = ({ label, children }: { label: string; children: React.ReactNode }) => {
  const { theme } = useSettings();
  return <label className="block space-y-1.5"><span className={sectionTitleClass(theme)}>{label}</span>{children}</label>;
};
const SelectField = FieldLabel;
const Field = ({ label, value, set, secret = false, placeholder = '' }: { label: string; value: string; set: (value: string) => void; secret?: boolean; placeholder?: string }) => {
  const { theme } = useSettings();
  return <FieldLabel label={label}><input type={secret ? 'password' : 'text'} className={inputClass(theme)} value={value} placeholder={placeholder} onChange={event => set(event.target.value)} /></FieldLabel>;
};
const NumberField = ({ label, value, set }: { label: string; value: number; set: (value: number) => void }) => {
  const { theme } = useSettings();
  return <FieldLabel label={label}><input type="number" min="1" className={inputClass(theme)} value={value} onChange={event => set(Number(event.target.value))} /></FieldLabel>;
};
