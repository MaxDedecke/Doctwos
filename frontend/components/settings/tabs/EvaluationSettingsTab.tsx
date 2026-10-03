"use client";

import type { ChatFeedbackDiagnosticSettings, ChatFeedbackReview } from '@/types/domain';
import { API_URL, api } from '@/app/services/api';
import { ListPager } from '@/components/settings/ListPager';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { ChevronDown, Loader2, MessageSquareWarning, RefreshCw } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';

// Die Liste kann sehr groß werden: Es wird immer nur eine Seite geladen und gerendert,
// Blättern und Suche laufen serverseitig.
export const FEEDBACK_PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

export const EvaluationSettingsTab: React.FC = () => {
  const { language, t } = useLanguage();
  const { theme, currentUser, showToast } = useSettings();
  const [entries, setEntries] = useState<ChatFeedbackReview[]>([]);
  const [total, setTotal] = useState(0);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const requestCounter = useRef(0);
  // Toast/Übersetzung nur beim Fehler nötig; über ein Ref, damit ihre (ggf. pro Render
  // neue) Identität das Nachladen der Liste nicht auslöst.
  const notifyRef = useRef({ showToast, t });
  useEffect(() => {
    notifyRef.current = { showToast, t };
  });
  const [diagnosticSettings, setDiagnosticSettings] = useState<ChatFeedbackDiagnosticSettings | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const isDark = theme === 'dark';

  // Der Entprellzeitgeber läuft auch beim Öffnen einmal ab. Die Seite wird nur zurückgesetzt, wenn sich die
  // Suche wirklich geändert hat; sonst würde ein früh gewähltes Blättern auf Seite 1 zurückspringen.
  const appliedQuery = useRef('');
  useEffect(() => {
    const timer = setTimeout(() => {
      const next = queryInput.trim();
      if (next === appliedQuery.current) return;
      appliedQuery.current = next;
      setQuery(next);
      setPage(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [queryInput]);

  const isAdmin = Boolean(currentUser?.is_admin);
  const refresh = useCallback(async () => {
    if (!isAdmin) return;
    const requestId = ++requestCounter.current;
    setLoading(true);
    try {
      const res = await api.getNegativeChatFeedback({
        limit: FEEDBACK_PAGE_SIZE,
        offset: page * FEEDBACK_PAGE_SIZE,
        ...(query ? { q: query } : {}),
      });
      if (requestId !== requestCounter.current) return; // veraltete Antwort
      const nextTotal = res.data.total ?? res.data.entries?.length ?? 0;
      setEntries(res.data.entries || []);
      setTotal(nextTotal);
      setSearchTruncated(Boolean(res.data.search_truncated));
      const lastPage = Math.max(0, Math.ceil(nextTotal / FEEDBACK_PAGE_SIZE) - 1);
      if (page > lastPage) setPage(lastPage);
    } catch (err) {
      if (requestId !== requestCounter.current) return;
      console.error('Failed to load negative chat feedback', err);
      notifyRef.current.showToast(notifyRef.current.t('settings.evaluationTab.feedbackLoadFailed'), 'error', err);
    } finally {
      if (requestId === requestCounter.current) setLoading(false);
    }
  }, [isAdmin, page, query]);

  const refreshDiagnosticSettings = async () => {
    if (!currentUser?.is_admin) return;
    try {
      const res = await api.getFeedbackDiagnosticSettings();
      setDiagnosticSettings(res.data);
    } catch (err) {
      console.error('Failed to load feedback diagnostic settings', err);
    }
  };

  // Load sensitive review data only while an administrator has this tab open.
  useEffect(() => {
    if (!isAdmin) return;
    (async () => {
      await refresh();
    })();
  }, [isAdmin, refresh]);

  useEffect(() => {
    if (!isAdmin) return;
    (async () => {
      await refreshDiagnosticSettings();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const saveDiagnosticSettings = async (next: Omit<ChatFeedbackDiagnosticSettings, 'updated_at'>) => {
    setSettingsSaving(true);
    try {
      const res = await api.updateFeedbackDiagnosticSettings(next);
      setDiagnosticSettings(res.data);
      showToast(t('settings.evaluationTab.diagnosticsSaved'), 'success');
    } catch (err) {
      console.error('Failed to save feedback diagnostic settings', err);
      showToast(t('settings.evaluationTab.diagnosticsSaveFailed'), 'error', err);
    } finally {
      setSettingsSaving(false);
    }
  };

  const deleteDiagnosticCases = async () => {
    if (!confirm(t('settings.evaluationTab.diagnosticsDeleteConfirm'))) return;
    try {
      const res = await api.deleteFeedbackDiagnosticCases();
      showToast(t('settings.evaluationTab.diagnosticsDeleted', { count: res.data.deleted }), 'success');
    } catch (err) {
      showToast(t('settings.evaluationTab.diagnosticsDeleteFailed'), 'error', err);
    }
  };

  const muted = isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600';
  const border = isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200';
  const surface = isDark ? 'bg-ds-zinc-950/30' : 'bg-ds-zinc-50';

  if (!currentUser?.is_admin) return null;

  return (
    <div className="space-y-5 animate-in fade-in duration-200">
      <section className={cn('rounded-lg border p-3 sm:p-4', border, surface)}>
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h4 className={cn('flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide', muted)}>
              <MessageSquareWarning className="h-3.5 w-3.5" />{t('settings.evaluationTab.feedbackTitle')}
            </h4>
            <p className={cn('mt-1 max-w-3xl text-[0.625rem]', muted)}>{t('settings.evaluationTab.feedbackDescription')}</p>
          </div>
          <Button type="button" size="sm" variant="outline" disabled={loading} onClick={() => void refresh()}
            className={cn('h-7 shrink-0 gap-1.5 px-2.5 text-[0.625rem] focus:ring-0', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-300 hover:bg-ds-zinc-800' : 'border-ds-zinc-200 bg-white text-ds-zinc-700 hover:bg-ds-zinc-100')}>
            {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}{t('settings.evaluationTab.feedbackRefresh')}
          </Button>
        </div>

        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className={cn('text-[0.625rem]', muted)}>{t('settings.evaluationTab.feedbackTotal', { total })}</p>
          <input type="search" value={queryInput} onChange={event => setQueryInput(event.target.value)}
            placeholder={t('settings.evaluationTab.feedbackSearch')}
            aria-label={t('settings.evaluationTab.feedbackSearch')}
            className={cn('h-8 w-full rounded-md border px-2 text-xs outline-none focus:border-ds-indigo-500 sm:w-64', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100 placeholder:text-ds-zinc-500' : 'border-ds-zinc-300 bg-white text-ds-zinc-900 placeholder:text-ds-zinc-400')} />
        </div>

        {loading && entries.length === 0 ? (
          <p className={cn('py-6 text-center text-xs', muted)}>{t('settings.evaluationTab.feedbackLoading')}</p>
        ) : entries.length === 0 ? (
          <div className={cn('rounded-lg border p-4 text-center text-xs', border, muted)}>{t(query ? 'settings.evaluationTab.feedbackNoMatches' : 'settings.evaluationTab.feedbackEmpty')}</div>
        ) : (
          <div className={cn('max-h-[52vh] space-y-2 overflow-y-auto overscroll-contain rounded-md border p-2', border)}>
            {entries.map(entry => (
              <details key={entry.message_id} className={cn('group rounded-md border p-3', border, surface)}>
                <summary className="flex cursor-pointer list-none items-start gap-2 outline-none [&::-webkit-details-marker]:hidden">
                  <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180" />
                  <span className="min-w-0 flex-1">
                    <span className={cn('flex flex-wrap justify-between gap-x-3 gap-y-1 text-[0.5625rem]', muted)}>
                      <span>{t('settings.evaluationTab.feedbackSession', { id: entry.session_label })}</span>
                      <time>{entry.created_at ? new Date(entry.created_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US') : ''}</time>
                    </span>
                    <span className="mt-1 block line-clamp-2 text-xs font-medium">{entry.question || t('settings.evaluationTab.feedbackQuestionMissing')}</span>
                  </span>
                </summary>
                <div className="mt-3 space-y-3 border-t border-ds-zinc-700/40 pt-3">
                  <div>
                    <p className="text-[0.5625rem] font-bold uppercase text-ds-zinc-500">{t('settings.evaluationTab.feedbackQuestion')}</p>
                    <p className={cn('whitespace-pre-wrap break-words text-xs', muted)}>{entry.question || t('settings.evaluationTab.feedbackQuestionMissing')}</p>
                  </div>
                  <div>
                    <p className="text-[0.5625rem] font-bold uppercase text-ds-zinc-500">{t('settings.evaluationTab.feedbackAnswer')}</p>
                    <p className={cn('max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded border p-2 text-xs', border, isDark ? 'text-ds-zinc-300' : 'text-ds-zinc-700')}>{entry.answer}</p>
                  </div>
                  <details className={cn('rounded border px-2.5 py-2 text-[0.625rem]', border)}>
                    <summary className="cursor-pointer font-medium text-ds-zinc-500">{t('settings.evaluationTab.feedbackEvidence')}</summary>
                    <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.625rem]">{JSON.stringify({ sources: entry.sources_json, metadata: entry.metadata_json }, null, 2)}</pre>
                  </details>
                </div>
              </details>
            ))}
          </div>
        )}

        {searchTruncated && query && <p className={cn('mt-2 text-[0.625rem]', muted)}>{t('settings.evaluationTab.feedbackSearchTruncated')}</p>}
        <div className="mt-2">
          <ListPager page={page} pageSize={FEEDBACK_PAGE_SIZE} shown={entries.length} total={total} loading={loading} theme={theme} onPageChange={setPage} />
        </div>
      </section>

      {diagnosticSettings && <section className={cn('space-y-3 rounded-lg border p-3 sm:p-4', border, surface)}>
        <div>
          <h4 className={cn('text-xs font-bold uppercase tracking-wide', muted)}>{t('settings.evaluationTab.diagnosticsTitle')}</h4>
          <p className="mt-0.5 text-[0.625rem] text-ds-zinc-500">{t('settings.evaluationTab.diagnosticsDescription')}</p>
        </div>
        <label className="flex cursor-pointer items-start gap-2 text-xs">
          <input type="checkbox" checked={diagnosticSettings.collection_enabled} disabled={settingsSaving}
            onChange={event => void saveDiagnosticSettings({ collection_enabled: event.target.checked, support_export_enabled: event.target.checked && diagnosticSettings.support_export_enabled, retention_days: diagnosticSettings.retention_days })} />
          <span><span className="font-medium">{t('settings.evaluationTab.diagnosticsCollect')}</span><span className="block text-[0.625rem] text-ds-zinc-500">{t('settings.evaluationTab.diagnosticsCollectDescription')}</span></span>
        </label>
        <label className="flex cursor-pointer items-start gap-2 text-xs">
          <input type="checkbox" checked={diagnosticSettings.support_export_enabled} disabled={!diagnosticSettings.collection_enabled || settingsSaving}
            onChange={event => void saveDiagnosticSettings({ collection_enabled: diagnosticSettings.collection_enabled, support_export_enabled: event.target.checked, retention_days: diagnosticSettings.retention_days })} />
          <span><span className="font-medium">{t('settings.evaluationTab.diagnosticsExport')}</span><span className="block text-[0.625rem] text-ds-zinc-500">{t('settings.evaluationTab.diagnosticsExportDescription')}</span></span>
        </label>
        <label className="block text-[0.625rem] text-ds-zinc-500">{t('settings.evaluationTab.diagnosticsRetention')}
          <input type="number" min={1} max={365} value={diagnosticSettings.retention_days} disabled={settingsSaving}
            onChange={event => setDiagnosticSettings({ ...diagnosticSettings, retention_days: Math.max(1, Math.min(365, Number(event.target.value) || 1)) })}
            onBlur={() => void saveDiagnosticSettings({ collection_enabled: diagnosticSettings.collection_enabled, support_export_enabled: diagnosticSettings.support_export_enabled, retention_days: diagnosticSettings.retention_days })}
            className={cn('ml-2 h-7 w-16 rounded border px-2 text-xs', isDark ? 'border-ds-zinc-700 bg-ds-zinc-900' : 'border-ds-zinc-300 bg-white')} />
        </label>
        <div className="flex flex-wrap gap-3">
          {diagnosticSettings.collection_enabled && diagnosticSettings.support_export_enabled && <a href={`${API_URL}/feedback-diagnostics/export`} download className="text-[0.625rem] text-ds-indigo-500 hover:underline">{t('settings.evaluationTab.diagnosticsDownload')}</a>}
          <button type="button" onClick={() => void deleteDiagnosticCases()} className="text-[0.625rem] text-ds-red-500 hover:underline">{t('settings.evaluationTab.diagnosticsDelete')}</button>
        </div>
      </section>}
    </div>
  );
};
