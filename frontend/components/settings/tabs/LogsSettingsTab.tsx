"use client";

import React, { useState, useEffect } from 'react';
import {
  Download, Loader2, FileText, Activity, CheckCircle2,
  AlertTriangle, ClipboardList, Terminal, RefreshCw, ShieldCheck, Clock3,
} from 'lucide-react';
import { cn, copyToClipboard } from "@/lib/utils";
import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from "@/components/ui/button";

// Aus SettingsModal herausgelöster 'logs'-Tab (docs/TECH_DEBT_CLEANUP_PLAN.md §5,
// Schritt 2). Logs-lokaler Zustand (activeLogSource, refreshingLogs, diagnostics*),
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

  const [activeLogSource, setActiveLogSource] = useState<any | null>(null);
  const [refreshingLogs, setRefreshingLogs] = useState<boolean>(false);
  const [diagnosticsRun, setDiagnosticsRun] = useState<any | null>(null);
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState<boolean>(false);
  const [mcpAuditEntries, setMcpAuditEntries] = useState<any[]>([]);
  const [mcpAuditRetentionDays, setMcpAuditRetentionDays] = useState<number | null>(null);
  const [mcpAuditLoading, setMcpAuditLoading] = useState<boolean>(false);

  const refreshKnowledgeSources = async () => {
    setRefreshingLogs(true);
    try {
      const res = await api.getKnowledgeSources();
      setConnectedSources(res.data);
      if (activeLogSource) {
        const updatedSource = res.data.find((s: any) => s.id === activeLogSource.id);
        if (updatedSource) {
          setActiveLogSource(updatedSource);
        }
      }
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
  }, [activeLogSource?.id]);

  const refreshMcpAuditLogs = async () => {
    if (!currentUser?.is_admin) return;
    setMcpAuditLoading(true);
    try {
      const res = await api.getMcpToolAuditLogs();
      setMcpAuditEntries(res.data?.entries || []);
      setMcpAuditRetentionDays(typeof res.data?.retention_days === 'number' ? res.data.retention_days : null);
    } catch (err) {
      console.error("Failed to reload MCP audit logs", err);
    } finally {
      setMcpAuditLoading(false);
    }
  };

  useEffect(() => {
    if (!currentUser?.is_admin) return;
    (async () => {
      await refreshMcpAuditLogs();
    })();
    const interval = setInterval(refreshMcpAuditLogs, 10000);
    return () => clearInterval(interval);
    // The admin flag is the only lifecycle input; refreshMcpAuditLogs is a
    // component-local action and intentionally not a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.is_admin]);

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
      showToast(t('settings.logsTab.diagnosticsStartFailedToast'), "error");
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* System status */}
      <div className="space-y-3">
        <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.logsTab.systemEnvTitle')}</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {[
            { label: 'FastAPI Backend-API', value: 'http://82.165.216.180:8000', status: backendStatus === 'connected' ? t('settings.logsTab.statusOnline') : t('settings.logsTab.statusError') },
            { label: 'Ollama LLM-Service', value: 'http://ollama:11434', status: backendStatus === 'connected' ? t('settings.logsTab.statusOnline') : t('settings.logsTab.statusChecking') },
            { label: 'PostgreSQL Vector-DB', value: 'postgresql://admin:***@db:5432/doctus', status: t('settings.logsTab.statusReady') },
            { label: 'Redis Celery Broker', value: 'redis://redis:6379/0', status: t('settings.logsTab.statusConnected') }
          ].map((item, idx) => (
            <div key={idx} className={cn(
              "p-3 border rounded-lg space-y-1 transition-colors",
              theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
            )}>
              <div className="flex items-center justify-between text-[9px]">
                <span className="text-ds-zinc-500 font-bold uppercase">{item.label}</span>
                <span className={cn(
                  "font-bold uppercase tracking-wider text-[8px] px-1 rounded-sm",
                  item.status === t('settings.logsTab.statusOnline') || item.status === t('settings.logsTab.statusReady') || item.status === t('settings.logsTab.statusConnected')
                    ? "bg-ds-emerald-500/10 text-ds-emerald-505"
                    : "bg-ds-amber-500/10 text-ds-amber-505"
                )}>{item.status}</span>
              </div>
              <p className={cn("font-mono text-[10px] truncate", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-600")}>{item.value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Diagnostics bundle (admin-only: contains DB metadata + service logs) */}
      {currentUser?.is_admin && (
        <div className={cn(
          "p-3 border rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors",
          theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
        )}>
          <div className="space-y-0.5">
            <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
              {t('settings.logsTab.diagnosticsTitle')}
            </h4>
            <p className={cn("text-[10px]", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>
              {t('settings.logsTab.diagnosticsDescription')}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            {diagnosticsRun?.status === 'completed' && (
              <a
                href={`${API_URL}/diagnostics/runs/${diagnosticsRun.id}/download`}
                download
                className={cn(
                  "h-7 text-[10px] px-2.5 flex items-center gap-1.5 rounded-md border font-medium",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700"
                )}
              >
                <Download className="w-3 h-3" />
                {t('settings.logsTab.diagnosticsDownload')}
              </a>
            )}
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={diagnosticsGenerating}
              onClick={handleGenerateDiagnostics}
              className={cn(
                "h-7 text-[10px] px-2.5 flex items-center gap-1.5 focus:ring-0",
                theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700"
              )}
            >
              {diagnosticsGenerating ? <Loader2 className="w-3 h-3 animate-spin" /> : <FileText className="w-3 h-3" />}
              {diagnosticsGenerating ? t('settings.logsTab.diagnosticsGenerating') : t('settings.logsTab.diagnosticsGenerate')}
            </Button>
          </div>
        </div>
      )}

      {/* MCP audit trail (admin-only; arguments are redacted server-side). */}
      {currentUser?.is_admin && (
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className={cn("text-xs font-bold uppercase tracking-wide flex items-center gap-1.5", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>
                <ShieldCheck className="w-3.5 h-3.5 text-ds-indigo-500" />
                {t('settings.logsTab.mcpAuditTitle')}
              </h4>
              <p className={cn("text-[10px] mt-1", theme === 'dark' ? "text-ds-zinc-500" : "text-ds-zinc-500")}>
                {t('settings.logsTab.mcpAuditDescription', { days: mcpAuditRetentionDays ?? '—' })}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={refreshMcpAuditLogs}
              disabled={mcpAuditLoading}
              className={cn(
                "h-7 text-[10px] px-2.5 flex items-center gap-1.5 shrink-0 focus:ring-0",
                theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700"
              )}
            >
              {mcpAuditLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
              {t('settings.logsTab.mcpAuditRefresh')}
            </Button>
          </div>

          {mcpAuditLoading && mcpAuditEntries.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-ds-zinc-500 p-4 border rounded-lg">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-ds-indigo-500" />
              {t('settings.logsTab.mcpAuditLoading')}
            </div>
          ) : mcpAuditEntries.length === 0 ? (
            <p className={cn(
              "text-xs italic p-4 border rounded-lg border-dashed text-center",
              theme === 'dark' ? "text-ds-zinc-500 border-ds-zinc-800" : "text-ds-zinc-400 border-ds-zinc-200"
            )}>
              {t('settings.logsTab.mcpAuditEmpty')}
            </p>
          ) : (
            <div className="space-y-2">
              {mcpAuditEntries.map((entry) => {
                const successful = entry.status === 'success';
                const formattedTime = entry.created_at
                  ? new Date(entry.created_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US')
                  : '—';
                return (
                  <div
                    key={entry.id}
                    className={cn(
                      "border rounded-lg p-3 space-y-2",
                      theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200"
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px]">
                      <span className={cn("font-mono font-bold", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>{entry.tool_name}</span>
                      <span className="text-ds-zinc-500">{entry.server_name}</span>
                      <span className={cn(
                        "px-1.5 py-0.5 rounded border font-bold uppercase",
                        successful ? "bg-ds-emerald-500/10 text-ds-emerald-455 border-ds-emerald-500/20" : "bg-ds-rose-500/10 text-ds-rose-455 border-ds-rose-500/20"
                      )}>
                        {successful ? t('settings.logsTab.mcpAuditSuccess') : t('settings.logsTab.mcpAuditError')}
                      </span>
                      <span className="ml-auto flex items-center gap-1 text-ds-zinc-500">
                        <Clock3 className="w-3 h-3" />{formattedTime}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-ds-zinc-500">
                      <span>{t('settings.logsTab.mcpAuditUser', { user: entry.user_name || '—' })}</span>
                      <span>{t('settings.logsTab.mcpAuditDuration', { duration: entry.duration_ms ?? 0 })}</span>
                      {entry.project_name && <span>{t('settings.logsTab.mcpAuditProject', { project: entry.project_name })}</span>}
                      {entry.trace_id && <span className="font-mono">trace: {entry.trace_id}</span>}
                    </div>
                    <pre className={cn(
                      "max-h-32 overflow-auto rounded border p-2 text-[10px] leading-relaxed whitespace-pre-wrap break-all",
                      theme === 'dark' ? "bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-600"
                    )}>
                      {JSON.stringify(entry.arguments ?? {}, null, 2)}
                    </pre>
                    {entry.error_message && <p className="text-[10px] text-ds-rose-500 break-all">{entry.error_message}</p>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Knowledge source log statuses */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-400" : "text-ds-zinc-500")}>{t('settings.logsTab.indexingLogsTitle')}</h4>
          {refreshingLogs && (
            <span className="text-[10px] text-ds-zinc-500 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin text-ds-indigo-500" /> {t('settings.logsTab.refreshing')}
            </span>
          )}
        </div>
        <div className="space-y-2.5">
          {connectedSources.length === 0 ? (
            <p className={cn(
              "text-xs italic p-4 border rounded-lg border-dashed text-center",
              theme === 'dark' ? "text-ds-zinc-500 border-ds-zinc-800" : "text-ds-zinc-400 border-ds-zinc-200"
            )}>
              {t('settings.logsTab.noSourcesConfigured')}
            </p>
          ) : (
            connectedSources.map((src: any) => {
              const status = src.sync_status || 'pending';
              let statusLabel = t('settings.logsTab.statusPending');
              let statusColorClass = theme === 'dark'
                ? 'bg-ds-zinc-800 text-ds-zinc-400 border-ds-zinc-700/50'
                : 'bg-ds-zinc-100 text-ds-zinc-500 border-ds-zinc-200';
              let statusIcon = <Activity className="w-3 h-3 shrink-0" />;

              if (status === 'syncing') {
                statusLabel = src.progress_message || t('settings.logsTab.statusSyncingDefault');
                statusColorClass = 'bg-ds-blue-500/10 text-ds-blue-450 border-ds-blue-500/20';
                statusIcon = (
                  <div className="flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin shrink-0 text-ds-blue-500" />
                    {src.progress > 0 && <span className="font-bold text-[9px]">{src.progress}%</span>}
                  </div>
                );
              } else if (status === 'completed') {
                statusLabel = t('settings.logsTab.statusSuccess');
                statusColorClass = 'bg-ds-emerald-500/10 text-ds-emerald-455 border-ds-emerald-500/20';
                statusIcon = <CheckCircle2 className="w-3 h-3 shrink-0 text-ds-emerald-400" />;
              } else if (status === 'error') {
                statusLabel = t('settings.logsTab.statusErrorLabel');
                statusColorClass = 'bg-ds-rose-500/10 text-ds-rose-455 border-ds-rose-500/20';
                statusIcon = <AlertTriangle className="w-3 h-3 shrink-0 text-ds-rose-400" />;
              }

              const formattedTime = src.last_synced_at
                ? new Date(src.last_synced_at).toLocaleString(language === 'de' ? 'de-DE' : 'en-US')
                : t('settings.logsTab.neverSynced');

              return (
                <div
                  key={src.id}
                  className={cn(
                    "p-3 border rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors",
                    theme === 'dark' ? "bg-ds-zinc-950/20 border-ds-zinc-800" : "bg-ds-zinc-50 border-ds-zinc-200",
                    activeLogSource?.id === src.id && (theme === 'dark' ? "border-ds-indigo-500/40 bg-ds-indigo-500/5" : "border-ds-indigo-400 bg-ds-indigo-50/20")
                  )}
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={cn("font-bold text-xs", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-800")}>{src.name}</span>
                      <span className={cn("text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border leading-none",
                        theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400" : "bg-ds-zinc-150 border-ds-zinc-200 text-ds-zinc-500"
                      )}>
                        {src.type}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-ds-zinc-500">
                      <span>{t('settings.logsTab.lastSyncLabel', { time: formattedTime })}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                    <div className={cn("flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-sm border", statusColorClass)}>
                      {statusIcon}
                      <span>{statusLabel}</span>
                    </div>

                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setActiveLogSource(activeLogSource?.id === src.id ? null : src)}
                      className={cn(
                        "h-7 text-[10px] px-2.5 flex items-center gap-1.5 focus:ring-0",
                        theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700"
                      )}
                    >
                      <ClipboardList className="w-3 h-3" />
                      {activeLogSource?.id === src.id ? t('settings.logsTab.hideLog') : t('settings.logsTab.showLog')}
                    </Button>

                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={status === 'syncing'}
                      onClick={async () => {
                        try {
                          await api.syncKnowledgeSource(src.id);
                          showToast(t('settings.logsTab.syncStartedToast'), "success");
                          refreshKnowledgeSources();
                        } catch (err) {
                          showToast(t('settings.logsTab.syncStartFailedToast'), "error");
                        }
                      }}
                      className={cn(
                        "h-7 w-7 p-0 flex items-center justify-center focus:ring-0",
                        theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300" : "bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700"
                      )}
                      title={t('settings.logsTab.syncNowTitle')}
                    >
                      <RefreshCw className={cn("w-3 h-3", status === 'syncing' && "animate-spin")} />
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Log details terminal */}
      {activeLogSource && (
        <div className={cn(
          "space-y-3 pt-4 border-t animate-in slide-in-from-bottom duration-250",
          theme === 'dark' ? "border-ds-zinc-800/80" : "border-ds-zinc-200"
        )}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-ds-indigo-500" />
              <h4 className={cn("text-xs font-bold uppercase tracking-wide", theme === 'dark' ? "text-ds-zinc-200" : "text-ds-zinc-700")}>
                {t('settings.logsTab.logTitle', { name: activeLogSource.name })}
              </h4>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={async () => {
                  const ok = await copyToClipboard(activeLogSource.sync_log || '');
                  showToast(t(ok ? 'settings.logsTab.logCopiedToast' : 'settings.toast.passwordCopyFailed'), ok ? "success" : "error");
                }}
                className={cn(
                  "h-7 text-[10px] px-2 flex items-center gap-1 focus:ring-0",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-600 hover:bg-ds-zinc-100"
                )}
              >
                {t('common.copy')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={refreshKnowledgeSources}
                disabled={refreshingLogs}
                className={cn(
                  "h-7 text-[10px] px-2 flex items-center gap-1 focus:ring-0",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-600 hover:bg-ds-zinc-100"
                )}
              >
                {refreshingLogs ? <Loader2 className="w-3 h-3 animate-spin text-ds-indigo-500" /> : <RefreshCw className="w-3 h-3" />}
                {t('common.refresh')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setActiveLogSource(null)}
                className={cn(
                  "h-7 text-[10px] px-2 flex items-center gap-1 focus:ring-0",
                  theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-600 hover:bg-ds-zinc-100"
                )}
              >
                {t('common.close')}
              </Button>
            </div>
          </div>

          {activeLogSource.last_error && (
            <div className="p-3.5 bg-ds-rose-500/10 border border-ds-rose-500/20 text-ds-rose-500 rounded-lg text-xs flex gap-2.5">
              <AlertTriangle className="w-4 h-4 shrink-0 text-ds-rose-500 mt-0.5" />
              <div className="min-w-0">
                <p className="font-bold uppercase tracking-wide text-[9px] text-ds-rose-455">{t('settings.logsTab.lastErrorLabel')}</p>
                <p className="font-mono text-[10px] mt-0.5 leading-relaxed break-all">{activeLogSource.last_error}</p>
              </div>
            </div>
          )}

          <div className="p-4 rounded-lg border font-mono text-[10px] leading-relaxed overflow-hidden whitespace-pre-wrap bg-ds-zinc-950 text-ds-zinc-300 border-ds-zinc-800">
            {activeLogSource.sync_log
              ? activeLogSource.sync_log.split('\n').filter(Boolean).slice(-28).join('\n')
              : t('settings.logsTab.noLogsPlaceholder')}
          </div>
        </div>
      )}
    </div>
  );
};
