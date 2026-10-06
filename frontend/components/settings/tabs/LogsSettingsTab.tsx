"use client";
import type { DiagnosticsRun, KnowledgeSource } from '@/types/domain';

import { api, API_URL } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { activeCardClass, badgeClass, cardClass, emptyStateClass, secondaryButtonClass, sectionTitleClass } from '@/components/settings/settingsStyles';
import { SyncLogViewer } from '@/components/settings/SyncLogViewer';
import { Button } from "@/components/ui/button";
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn, copyToClipboard } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Terminal,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';

// Aus SettingsModal herausgelöster 'logs'-Tab. Logs-lokaler Zustand (activeLogSource, refreshingLogs, diagnostics*),
// handleGenerateDiagnostics und das 5s-Polling wandern mit hierher. connectedSources
// ist geteilter App-Zustand und kommt via useSettings() — refreshKnowledgeSources
// schreibt hier hinein. Der sources-Tab pollt connectedSources weiterhin selbst
// (eigener Effekt im Modal), unabhängig von diesem Tab.
export const LogsSettingsTab: React.FC = () => {
  const { language, t } = useLanguage();
  const {
    theme,
    backendStatus,
    currentUser,
    connectedSources,
    setConnectedSources,
    showToast,
  } = useSettings();

  const [activeLogSourceId, setActiveLogSourceId] = useState<KnowledgeSource['id'] | null>(null);
  const [refreshingLogs, setRefreshingLogs] = useState<boolean>(false);
  const [diagnosticsRun, setDiagnosticsRun] = useState<DiagnosticsRun | null>(null);
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState<boolean>(false);

  const refreshKnowledgeSources = async () => {
    setRefreshingLogs(true);
    try {
      const res = await api.getKnowledgeSources();
      setConnectedSources(res.data);
    } catch (err) {
      console.error("Failed to reload knowledge sources", err);
    } finally {
      setRefreshingLogs(false);
    }
  };

  // Dieser Tab wird nur gerendert, wenn das Modal offen und logs aktiv ist —
  // der Effekt startet also beim Betreten des Tabs und räumt beim Verlassen auf.
  useEffect(() => {
    (async () => {
      await refreshKnowledgeSources();
    })();
    const interval = setInterval(() => {
      refreshKnowledgeSources();
    }, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ohne Auswahl (oder nach dem Entfernen der gewählten Quelle) zeigt der Log-Bereich die erste Quelle,
  // damit er beim Öffnen nie leer bleibt, solange es Quellen gibt.
  const activeLogSource = connectedSources.find((src) => src.id === activeLogSourceId) ?? connectedSources[0] ?? null;

  const handleGenerateDiagnostics = async () => {
    setDiagnosticsGenerating(true);
    setDiagnosticsRun(null);
    try {
      await api.generateDiagnosticsBundle();
      showToast(t('settings.logsTab.diagnosticsStartedToast'), "success");
      // Kein WebSocket/SSE für Task-Fortschritt vorhanden — kurzes Polling bis
      // completed/failed, gleiche Idee wie der bestehende Sync-Status-Refresh.
      const poll = async () => {
        try {
          const res = await api.getDiagnosticsRuns();
          const latest = res.data?.[0] || null;
          setDiagnosticsRun(latest);
          if (latest && (latest.status === 'completed' || latest.status === 'failed')) {
            setDiagnosticsGenerating(false);
            if (latest.status === 'failed') {
              showToast(t('settings.logsTab.diagnosticsFailedToast'), "error");
            }
            return;
          }
        } catch (err) {
          setDiagnosticsGenerating(false);
          return;
        }
        setTimeout(poll, 3000);
      };
      setTimeout(poll, 3000);
    } catch (err) {
      setDiagnosticsGenerating(false);
      showToast(t('settings.logsTab.diagnosticsStartFailedToast'), "error", err);
    }
  };

  const dark = theme === 'dark';
  const services = [
    { label: 'Backend-API', value: API_URL, ok: backendStatus === 'connected', text: backendStatus === 'connected' ? t('settings.logsTab.statusOnline') : t('settings.logsTab.statusError') },
    { label: 'Ollama', value: 'http://ollama:11434', ok: backendStatus === 'connected', text: backendStatus === 'connected' ? t('settings.logsTab.statusOnline') : t('settings.logsTab.statusChecking') },
    { label: 'PostgreSQL', value: 'db:5432', ok: true, text: t('settings.logsTab.statusReady') },
    { label: 'Redis', value: 'redis:6379', ok: true, text: t('settings.logsTab.statusConnected') },
  ];

  const sourceStatus = (src: KnowledgeSource) => {
    const status = src.sync_status || 'pending';
    if (status === 'syncing') {
      return {
        status, tone: 'accent' as const, label: src.progress_message || t('settings.logsTab.statusSyncingDefault'),
        icon: <Loader2 className="w-3 h-3 animate-spin shrink-0" />, progress: src.progress ?? 0,
      };
    }
    if (status === 'completed') return { status, tone: 'success' as const, label: t('settings.logsTab.statusSuccess'), icon: <CheckCircle2 className="w-3 h-3 shrink-0" />, progress: 0 };
    if (status === 'error') return { status, tone: 'danger' as const, label: t('settings.logsTab.statusErrorLabel'), icon: <AlertTriangle className="w-3 h-3 shrink-0" />, progress: 0 };
    return { status, tone: 'neutral' as const, label: t('settings.logsTab.statusPending'), icon: <Activity className="w-3 h-3 shrink-0" />, progress: 0 };
  };

  const formatTime = (src: KnowledgeSource) => src.last_synced_at
    ? new Date(src.last_synced_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US')
    : t('settings.logsTab.neverSynced');

  const startSync = async (src: KnowledgeSource) => {
    try {
      await api.syncKnowledgeSource(Number(src.id));
      showToast(t('settings.logsTab.syncStartedToast'), "success");
      refreshKnowledgeSources();
    } catch (err) {
      showToast(t('settings.logsTab.syncStartFailedToast'), "error", err);
    }
  };

  const activeStatus = activeLogSource ? sourceStatus(activeLogSource) : null;

  // Feste Höhe: Der Tab füllt den Dialog, die Quellenliste und das Log scrollen jeweils in sich.
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-4 animate-in fade-in duration-200">
      {/* Systemstatus und Diagnose in einer Zeile */}
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <h4 className={cn(sectionTitleClass(theme), 'mr-1')}>{t('settings.logsTab.systemEnvTitle')}</h4>
        {services.map((service) => (
          <span key={service.label} title={service.value} className={cn(cardClass(theme), 'inline-flex items-center gap-2 px-2.5 py-1 text-[0.6875rem]')}>
            <span aria-hidden="true" className={cn('h-1.5 w-1.5 rounded-full', service.ok ? 'bg-ds-emerald-500' : 'bg-ds-amber-500')} />
            <span className={cn('font-semibold', dark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>{service.label}</span>
            <span className="text-ds-zinc-500">{service.text}</span>
          </span>
        ))}

        {/* Diagnose-Bundle (nur Admin: enthält DB-Metadaten und Service-Logs) */}
        {currentUser?.is_admin && (
          <div className="ml-auto flex items-center gap-2" title={t('settings.logsTab.diagnosticsDescription')}>
            <span className={cn(sectionTitleClass(theme), 'hidden lg:inline')}>{t('settings.logsTab.diagnosticsTitle')}</span>
            {diagnosticsRun?.status === 'completed' && (
              <a href={`${API_URL}/diagnostics/runs/${diagnosticsRun.id}/download`} download
                className={cn(secondaryButtonClass(theme), 'border font-medium')}>
                <Download className="w-3 h-3" />{t('settings.logsTab.diagnosticsDownload')}
              </a>
            )}
            <Button type="button" size="sm" variant="outline" disabled={diagnosticsGenerating} onClick={handleGenerateDiagnostics} className={secondaryButtonClass(theme)}>
              {diagnosticsGenerating ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileText className="w-3 h-3" />}
              {diagnosticsGenerating ? t('settings.logsTab.diagnosticsGenerating') : t('settings.logsTab.diagnosticsGenerate')}
            </Button>
          </div>
        )}
      </div>

      {/* Quellen links, Log rechts */}
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,11rem)_minmax(0,1fr)] gap-4 md:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)] md:grid-rows-1">
        <section className="flex min-h-0 flex-col gap-2" aria-label={t('settings.logsTab.indexingLogsTitle')}>
          <div className="flex shrink-0 items-center justify-between gap-2">
            <h4 className={sectionTitleClass(theme)}>{t('settings.logsTab.indexingLogsTitle')}</h4>
            {refreshingLogs && (
              <span className="flex items-center gap-1 text-[0.625rem] text-ds-zinc-500">
                <Loader2 className="w-3 h-3 animate-spin text-ds-indigo-500" /> {t('settings.logsTab.refreshing')}
              </span>
            )}
          </div>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1">
            {connectedSources.length === 0 ? (
              <p className={cn(emptyStateClass(theme), 'border-dashed text-center')}>{t('settings.logsTab.noSourcesConfigured')}</p>
            ) : connectedSources.map((src) => {
              const info = sourceStatus(src);
              const selected = activeLogSource?.id === src.id;
              return (
                <div key={src.id} className={cn(selected ? activeCardClass(theme) : cardClass(theme), 'flex items-center gap-1 p-1.5')}>
                  <button type="button" aria-pressed={selected} onClick={() => setActiveLogSourceId(src.id)}
                    className="min-w-0 flex-1 rounded-md px-1.5 py-1 text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-ds-indigo-500">
                    <div className="flex items-center gap-2">
                      <span className={cn('truncate text-xs font-bold', dark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>{src.name}</span>
                      <span className={badgeClass('neutral')}>{src.type}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[0.625rem] text-ds-zinc-500">
                      <span className={cn(badgeClass(info.tone), 'inline-flex max-w-[11rem] items-center gap-1 normal-case tracking-normal')}>
                        {info.icon}
                        <span className="truncate">{info.label}</span>
                        {info.progress > 0 && <span>{info.progress}%</span>}
                      </span>
                      <span className="truncate">{t('settings.logsTab.lastSyncLabel', { time: formatTime(src) })}</span>
                    </div>
                  </button>
                  <Button type="button" size="icon" variant="ghost" disabled={info.status === 'syncing'} onClick={() => startSync(src)}
                    title={t('settings.logsTab.syncNowTitle')} aria-label={t('settings.logsTab.syncNowTitle')}
                    className="h-8 w-8 shrink-0 rounded-lg text-ds-zinc-500 hover:bg-ds-zinc-500/10">
                    <RefreshCw className={cn('w-3.5 h-3.5', info.status === 'syncing' && 'animate-spin')} />
                  </Button>
                </div>
              );
            })}
          </div>
        </section>

        <section className={cn(cardClass(theme), 'flex min-h-0 min-w-0 flex-col gap-3 p-3')}>
          {activeLogSource ? (
            <>
              <div className="flex shrink-0 items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <Terminal className="w-3.5 h-3.5 shrink-0 text-ds-indigo-500" />
                  <h4 className={cn(sectionTitleClass(theme), 'truncate')}>{t('settings.logsTab.logTitle', { name: activeLogSource.name })}</h4>
                  {activeStatus && <span className={cn(badgeClass(activeStatus.tone), 'hidden shrink-0 sm:inline-flex')}>{activeStatus.label}</span>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button type="button" size="sm" variant="outline" className={secondaryButtonClass(theme)}
                    onClick={async () => {
                      const ok = await copyToClipboard(activeLogSource.sync_log || '');
                      showToast(t(ok ? 'settings.logsTab.logCopiedToast' : 'settings.toast.passwordCopyFailed'), ok ? "success" : "error");
                    }}>
                    {t('common.copy')}
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={refreshKnowledgeSources} disabled={refreshingLogs} className={secondaryButtonClass(theme)}>
                    {refreshingLogs ? <Loader2 className="w-3 h-3 animate-spin text-ds-indigo-500" /> : <RefreshCw className="w-3 h-3" />}
                    {t('common.refresh')}
                  </Button>
                </div>
              </div>

              {activeLogSource.last_error && (
                <div className="flex shrink-0 gap-2.5 rounded-lg border border-ds-rose-500/20 bg-ds-rose-500/10 p-3 text-xs text-ds-rose-500">
                  <AlertTriangle className="mt-0.5 w-4 h-4 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[0.5625rem] font-bold uppercase tracking-wide">{t('settings.logsTab.lastErrorLabel')}</p>
                    <p className="mt-0.5 max-h-20 overflow-y-auto break-all font-mono text-[0.625rem] leading-relaxed">{activeLogSource.last_error}</p>
                  </div>
                </div>
              )}

              <div className="min-h-0 flex-1">
                <SyncLogViewer key={activeLogSource.id} log={activeLogSource.sync_log} />
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-xs text-ds-zinc-500">
              <Terminal className="w-5 h-5 opacity-40" />
              <p>{t('settings.logsTab.selectSourcePrompt')}</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
