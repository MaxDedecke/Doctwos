"use client";
import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from "@/lib/utils";
import { Loader2 } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';

interface Migration {
  id: number;
  status: string;
  target_model: string;
  previous_model?: string | null;
  total: number;
  done: number;
  error?: string | null;
}
interface MigrationState {
  models: Record<string, number>;
  without_embedding: number;
  project_profile?: { id: number; name: string; model: string } | null;
  migration?: Migration | null;
}
interface ProfileOption { id: number; name: string; model: string }
type Action = 'switch' | 'rollback' | 'cleanup' | 'cancel' | 'resume';

// Modellwechsel je Projekt (backend/api/embedding_migrations.py). Lesen dürfen Mitglieder, handeln nur Admins.
export const EmbeddingMigrationPanel: React.FC<{ projectId: number; isAdmin: boolean }> = ({ projectId, isAdmin }) => {
  const { t } = useLanguage();
  const { theme, showToast } = useSettings();
  const [state, setState] = useState<MigrationState | null>(null);
  const [profiles, setProfiles] = useState<ProfileOption[]>([]);
  const [target, setTarget] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setState((await api.getEmbeddingMigration(projectId)).data); }
    catch (error) { showToast(t('settings.projects.embedding.error'), 'error', error); }
  }, [projectId, showToast, t]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!isAdmin) return;
    api.getEmbeddingProfiles().then(res => setProfiles((res.data?.profiles ?? []) as ProfileOption[])).catch(() => setProfiles([]));
  }, [isAdmin]);
  const status = state?.migration?.status;
  useEffect(() => {
    if (status !== 'embedding') return;
    const timer = setInterval(() => { void load(); }, 5000);
    return () => clearInterval(timer);
  }, [status, load]);

  const run = async (call: () => Promise<unknown>) => {
    setBusy(true);
    try { await call(); await load(); }
    catch (error) { showToast(t('settings.projects.embedding.error'), 'error', error); }
    finally { setBusy(false); }
  };
  const act = (action: Action) => state?.migration && run(() => api.embeddingMigrationAction(projectId, state.migration!.id, action));

  if (!state) return <Loader2 className="w-4 h-4 animate-spin text-ds-indigo-500" />;
  const m = state.migration;
  const current = state.project_profile?.model ?? '—';
  const choices = profiles.filter(p => p.model !== current);
  const open = m && ['embedding', 'ready', 'switched', 'failed'].includes(m.status);
  const muted = theme === 'dark' ? 'text-ds-zinc-400' : 'text-ds-zinc-600';

  return (
    <div className="space-y-2 text-[0.6875rem]" data-testid="embedding-migration-panel">
      <p className="font-semibold">{t('settings.projects.embedding.title')}</p>
      <p className={muted}>{t('settings.projects.embedding.current', { model: current })}</p>
      <p className={muted}>
        {t('settings.projects.embedding.coverage')}: {Object.entries(state.models).map(([model, count]) => `${model} ${count}`).join(' · ') || '—'}
        {state.without_embedding > 0 && <> · {t('settings.projects.embedding.withoutEmbedding', { count: String(state.without_embedding) })}</>}
      </p>
      {m && m.status === 'embedding' && (
        <div className="space-y-1">
          <p>{t('settings.projects.embedding.progress', { model: m.target_model, done: String(m.done), total: String(m.total) })}</p>
          <div className="h-1.5 rounded bg-ds-zinc-500/20"><div className="h-1.5 rounded bg-ds-indigo-500" style={{ width: `${m.total ? Math.min(100, (100 * m.done) / m.total) : 0}%` }} /></div>
        </div>
      )}
      {m && m.status === 'ready' && <p>{t('settings.projects.embedding.ready', { model: m.target_model, previous: m.previous_model ?? '—' })}</p>}
      {m && m.status === 'switched' && <p>{t('settings.projects.embedding.switched', { model: m.target_model })}</p>}
      {m && m.status === 'rolled_back' && <p>{t('settings.projects.embedding.rolledBack', { model: m.previous_model ?? '—' })}</p>}
      {m && m.status === 'cancelled' && <p>{t('settings.projects.embedding.cancelled')}</p>}
      {m && m.status === 'cleaned' && <p>{t('settings.projects.embedding.cleaned')}</p>}
      {m?.error && <p className="text-ds-red-500 break-words">{t('settings.projects.embedding.failed', { error: m.error })}</p>}
      {isAdmin && (
        <div className="flex flex-wrap items-center gap-2">
          {m?.status === 'ready' && <Button size="sm" disabled={busy} onClick={() => act('switch')}>{t('settings.projects.embedding.switch')}</Button>}
          {m?.status === 'switched' && <Button size="sm" variant="outline" disabled={busy} onClick={() => act('rollback')}>{t('settings.projects.embedding.rollback')}</Button>}
          {m && ['switched', 'rolled_back'].includes(m.status) && <Button size="sm" variant="outline" disabled={busy} onClick={() => act('cleanup')}>{t('settings.projects.embedding.cleanup')}</Button>}
          {m && ['embedding', 'ready', 'failed'].includes(m.status) && <Button size="sm" variant="outline" disabled={busy} onClick={() => act('cancel')}>{t('settings.projects.embedding.cancel')}</Button>}
          {m?.status === 'failed' && <Button size="sm" disabled={busy} onClick={() => act('resume')}>{t('settings.projects.embedding.resume')}</Button>}
          {!open && (choices.length === 0 ? <span className={muted}>{t('settings.projects.embedding.noProfiles')}</span> : (
            <>
              <select aria-label={t('settings.projects.embedding.target')} value={target} onChange={e => setTarget(e.target.value)}
                className={cn('h-8 rounded border px-2 bg-transparent', theme === 'dark' ? 'border-ds-zinc-700' : 'border-ds-zinc-300')}>
                <option value="">{t('settings.projects.embedding.target')}</option>
                {choices.map(p => <option key={p.id} value={p.id}>{p.name} ({p.model})</option>)}
              </select>
              <Button size="sm" disabled={busy || !target} onClick={() => run(() => api.startEmbeddingMigration(projectId, Number(target)))}>{t('settings.projects.embedding.start')}</Button>
            </>
          ))}
        </div>
      )}
      <p className={muted}>{t('settings.projects.embedding.explain')}</p>
    </div>
  );
};
