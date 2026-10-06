"use client";

import { api } from '@/app/services/api';
import { Field, NumberField, SelectField, selectTriggerClass } from '@/components/settings/formFields';
import { cardClass, helpTextClass, primaryButtonClass, secondaryButtonClass } from '@/components/settings/settingsStyles';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { DeploymentCapabilities, DeploymentEngine, LlmDeployment } from '@/hooks/useLlmDeployments';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';
import React, { useMemo, useState } from 'react';

type Role = 'chat' | 'embedding';

interface Props {
  theme: string;
  role: Role;
  capabilities: DeploymentCapabilities;
  /** Vorhandene Deployments, damit die Container-Kennung eindeutig bleibt. */
  existing: LlmDeployment[];
  /** Fehler des Deployers (nicht erreichbar / nicht eingerichtet); verhindert das Anlegen. */
  deployerError: string | null;
  onCreated: (result: { profile: Record<string, unknown>; deployment: Record<string, unknown> }) => void;
  onCancel: () => void;
  showToast: (message: string, kind?: 'success' | 'error', error?: unknown) => void;
}

const MODEL_PLACEHOLDER: Record<Role, Record<DeploymentEngine, string>> = {
  chat: { ollama: 'qwen3:8b', llamacpp: 'unsloth/Qwen3-8B-GGUF:Q4_K_M', vllm: 'Qwen/Qwen2.5-Coder-14B-Instruct' },
  embedding: { ollama: 'bge-m3', llamacpp: 'bge-m3-q8_0.gguf', vllm: 'BAAI/bge-m3' },
};
const TOOL_PARSERS = ['hermes', 'llama3_json', 'mistral', 'qwen3_coder', 'pythonic'];

/** Container-Kennung aus dem Profilnamen: a-z, 0-9, Bindestrich; bei Kollision mit -2, -3 … */
export function deploymentSlug(displayName: string, fallback: string, taken: string[]): string {
  const base = (displayName.toLowerCase().replace(/ß/g, 'ss').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 26) || fallback);
  let slug = base.length < 2 ? `${base}-x` : base;
  for (let n = 2; taken.includes(slug); n += 1) slug = `${base.slice(0, 26)}-${n}`;
  return slug;
}

/** Formular für ein lokales Deployment (Ollama, vLLM oder llama.cpp) als LLM- oder Embedding-Profil. */
export function LocalDeploymentForm({ theme, role, capabilities, existing, deployerError, onCreated, onCancel, showToast }: Props) {
  const { t } = useLanguage();
  const [displayName, setDisplayName] = useState('');
  const [engine, setEngine] = useState<DeploymentEngine>('llamacpp');
  const [model, setModel] = useState('');
  const [gpu, setGpu] = useState(capabilities.gpu);
  const [contextLength, setContextLength] = useState(role === 'chat' ? 8192 : 8100);
  const [toolParser, setToolParser] = useState('hermes');
  const [dimension, setDimension] = useState(1024);
  const [busy, setBusy] = useState(false);

  const slug = useMemo(() => deploymentSlug(displayName, `${engine}-${role}`, existing.map(item => item.name)), [displayName, engine, role, existing]);
  const needsGpu = engine === 'vllm';
  const gpuMissing = (gpu || needsGpu) && !capabilities.gpu;
  const useGpu = needsGpu || gpu;
  const canSubmit = !busy && !deployerError && displayName.trim() && model.trim() && !gpuMissing;

  const submit = async () => {
    setBusy(true);
    try {
      const response = await api.createLlmDeployment({
        name: slug, display_name: displayName.trim(), engine, model: model.trim(), role, gpu: useGpu,
        context_length: contextLength, dimension,
        ...(engine === 'vllm' && role === 'chat' ? { tool_parser: toolParser } : {}),
      });
      onCreated(response.data as { profile: Record<string, unknown>; deployment: Record<string, unknown> });
    } catch (error) {
      showToast(t('settings.deployments.createFailed'), 'error', error);
    } finally {
      setBusy(false);
    }
  };

  return <div className={cn(cardClass(theme), 'space-y-4 p-4')}>
    <p className={helpTextClass}>{t(role === 'chat' ? 'settings.deployments.introChat' : 'settings.deployments.introEmbedding')}</p>
    {deployerError && <p role="alert" className="rounded-lg border border-ds-amber-500/30 bg-ds-amber-500/10 px-3 py-2 text-xs text-ds-amber-500">{t('settings.deployments.deployerUnavailable', { error: deployerError })}</p>}
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label={t('settings.profilesTab.profileNameLabel')} value={displayName} set={setDisplayName} placeholder={t('settings.deployments.namePlaceholder')} />
      <SelectField label={t('settings.deployments.engine')}>
        <Select value={engine} onValueChange={value => setEngine(value as DeploymentEngine)}>
          <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="llamacpp">llama.cpp</SelectItem>
            <SelectItem value="vllm">vLLM</SelectItem>
            <SelectItem value="ollama">Ollama</SelectItem>
          </SelectContent>
        </Select>
      </SelectField>
    </div>
    <p className={helpTextClass}>{t(`settings.deployments.engineHint.${engine}`)}</p>
    <Field label={t('settings.profilesTab.modelNameLabel')} value={model} set={setModel} placeholder={MODEL_PLACEHOLDER[role][engine]} />
    <p className={helpTextClass}>{t(`settings.deployments.modelHint.${engine}`)}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <NumberField label={t(role === 'chat' ? 'settings.profilesTab.llmContextLabel' : 'settings.profilesTab.embeddingContextLabel')} value={contextLength} set={setContextLength} />
      {role === 'embedding' && <NumberField label={t('settings.profilesTab.embeddingDimensionLabel')} value={dimension} set={setDimension} />}
      {engine === 'vllm' && role === 'chat' && <SelectField label={t('settings.deployments.toolParser')}>
        <Select value={toolParser} onValueChange={setToolParser}>
          <SelectTrigger className={selectTriggerClass}><SelectValue /></SelectTrigger>
          <SelectContent>{TOOL_PARSERS.map(parser => <SelectItem key={parser} value={parser}>{parser}</SelectItem>)}</SelectContent>
        </Select>
      </SelectField>}
    </div>
    <label className="flex items-center gap-2 text-xs">
      <input type="checkbox" checked={useGpu} disabled={needsGpu || !capabilities.gpu} onChange={event => setGpu(event.target.checked)} />
      <span>{t('settings.deployments.useGpu')}</span>
      {!capabilities.gpu && <span className="text-ds-zinc-500">{t('settings.deployments.noGpu')}</span>}
    </label>
    {gpuMissing && <p role="alert" className="text-xs text-ds-amber-500">{t('settings.deployments.gpuRequired')}</p>}
    {role === 'embedding' && <p className={helpTextClass}>{t('settings.deployments.dimensionHint')}</p>}
    <p className={cn(helpTextClass, 'font-mono')}>doctus-llm-{slug}</p>
    <div className="flex justify-end gap-2">
      <Button variant="outline" onClick={onCancel} className={cn(secondaryButtonClass(theme), 'h-9 text-xs')}>{t('common.cancel')}</Button>
      <Button onClick={submit} disabled={!canSubmit} className={primaryButtonClass}>
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{t('settings.deployments.create')}
      </Button>
    </div>
  </div>;
}
