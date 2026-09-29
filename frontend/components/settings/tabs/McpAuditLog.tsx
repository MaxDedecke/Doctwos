"use client";

import { api } from '@/app/services/api';
import { useSettings } from '@/components/settings/SettingsContext';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import type { McpAuditEntry } from '@/types/domain';
import { ChevronDown, ChevronLeft, ChevronRight, Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';

// Der Audit-Trail kann sehr groß werden. Es wird deshalb immer nur eine Seite
// mit PAGE_SIZE Einträgen vom Server geholt und gerendert; Blättern, Status- und
// Werkzeugfilter laufen serverseitig. Die Höhe des Listenbereichs ist begrenzt,
// damit das Layout des Tabs nicht mit der Datenmenge wächst.
export const MCP_AUDIT_PAGE_SIZE = 20;
const REFRESH_INTERVAL_MS = 10000;
const FILTER_DEBOUNCE_MS = 300;

type StatusFilter = 'all' | 'success' | 'error';

export const McpAuditLog: React.FC = () => {
  const { language, t } = useLanguage();
  const { theme, currentUser } = useSettings();
  const isAdmin = Boolean(currentUser?.is_admin);
  const dark = theme === 'dark';

  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [toolInput, setToolInput] = useState('');
  const [toolFilter, setToolFilter] = useState('');
  const [entries, setEntries] = useState<McpAuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const requestCounter = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setToolFilter(toolInput.trim());
      setPage(0);
    }, FILTER_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [toolInput]);

  const load = useCallback(async (silent: boolean) => {
    const requestId = ++requestCounter.current;
    if (!silent) setLoading(true);
    try {
      const res = await api.getMcpToolAuditLogs({
        limit: MCP_AUDIT_PAGE_SIZE,
        offset: page * MCP_AUDIT_PAGE_SIZE,
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
        ...(toolFilter ? { tool: toolFilter } : {}),
      });
      if (requestId !== requestCounter.current) return; // veraltete Antwort
      const nextTotal = typeof res.data?.total === 'number' ? res.data.total : (res.data?.entries?.length ?? 0);
      setEntries(res.data?.entries || []);
      setTotal(nextTotal);
      setRetentionDays(typeof res.data?.retention_days === 'number' ? res.data.retention_days : null);
      // Durch Retention-Bereinigung kann die aktuelle Seite verschwinden.
      const lastPage = Math.max(0, Math.ceil(nextTotal / MCP_AUDIT_PAGE_SIZE) - 1);
      if (page > lastPage) setPage(lastPage);
    } catch (err) {
      if (requestId === requestCounter.current) console.error('Failed to reload MCP audit logs', err);
    } finally {
      if (requestId === requestCounter.current) setLoading(false);
    }
  }, [page, statusFilter, toolFilter]);

  useEffect(() => {
    if (!isAdmin) return;
    (async () => {
      await load(false);
    })();
    const interval = setInterval(() => { void load(true); }, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isAdmin, load]);

  if (!isAdmin) return null;

  const pageCount = Math.max(1, Math.ceil(total / MCP_AUDIT_PAGE_SIZE));
  const from = total === 0 ? 0 : page * MCP_AUDIT_PAGE_SIZE + 1;
  const to = page * MCP_AUDIT_PAGE_SIZE + entries.length;
  const filtered = statusFilter !== 'all' || toolFilter !== '';
  const muted = dark ? 'text-ds-zinc-500' : 'text-ds-zinc-500';
  const panel = dark ? 'bg-ds-zinc-950/20 border-ds-zinc-800' : 'bg-ds-zinc-50 border-ds-zinc-200';
  const control = dark
    ? 'bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300'
    : 'bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700';
  const locale = language === 'de' ? 'de-DE' : 'en-US';

  const changeStatus = (next: StatusFilter) => {
    setStatusFilter(next);
    setPage(0);
    setExpandedId(null);
  };

  return (
    <div className="space-y-3" data-testid="mcp-audit-log">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className={cn('text-xs font-bold uppercase tracking-wide flex items-center gap-1.5', dark ? 'text-ds-zinc-400' : 'text-ds-zinc-500')}>
            <ShieldCheck className="w-3.5 h-3.5 text-ds-indigo-500" />
            {t('settings.mcpAudit.title')}
          </h4>
          <p className={cn('text-[10px] mt-1', muted)}>
            {t('settings.mcpAudit.description', { days: retentionDays ?? '—' })}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => { void load(false); }}
          disabled={loading}
          className={cn('h-7 text-[10px] px-2.5 flex items-center gap-1.5 shrink-0 focus:ring-0', control)}
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          {t('settings.mcpAudit.refresh')}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t('settings.mcpAudit.statusFilter')} className="flex overflow-hidden rounded-md border text-[10px] font-medium">
          {(['all', 'success', 'error'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={statusFilter === option}
              onClick={() => changeStatus(option)}
              className={cn(
                'px-2.5 py-1 transition-colors',
                dark ? 'border-ds-zinc-800' : 'border-ds-zinc-200',
                statusFilter === option
                  ? 'bg-ds-indigo-600 text-white'
                  : dark ? 'bg-ds-zinc-900 text-ds-zinc-400 hover:bg-ds-zinc-800' : 'bg-ds-white text-ds-zinc-600 hover:bg-ds-zinc-100',
              )}
            >
              {t(`settings.mcpAudit.filter.${option}`)}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={toolInput}
          onChange={(event) => setToolInput(event.target.value)}
          placeholder={t('settings.mcpAudit.toolFilterPlaceholder')}
          aria-label={t('settings.mcpAudit.toolFilterPlaceholder')}
          maxLength={200}
          className={cn(
            'h-7 min-w-0 flex-1 rounded-md border px-2.5 text-[11px] outline-none focus:ring-1 focus:ring-ds-indigo-500 sm:max-w-xs',
            dark ? 'border-ds-zinc-800 bg-ds-zinc-900 text-ds-zinc-200 placeholder:text-ds-zinc-600' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-800 placeholder:text-ds-zinc-400',
          )}
        />
      </div>

      {loading && entries.length === 0 ? (
        <div className="flex items-center gap-2 text-xs text-ds-zinc-500 p-4 border rounded-lg">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-ds-indigo-500" />
          {t('settings.mcpAudit.loading')}
        </div>
      ) : entries.length === 0 ? (
        <p className={cn('text-xs italic p-4 border rounded-lg border-dashed text-center', dark ? 'text-ds-zinc-500 border-ds-zinc-800' : 'text-ds-zinc-400 border-ds-zinc-200')}>
          {filtered ? t('settings.mcpAudit.emptyFiltered') : t('settings.mcpAudit.empty')}
        </p>
      ) : (
        <div className={cn('max-h-[26rem] overflow-y-auto rounded-lg border divide-y', panel, dark ? 'divide-ds-zinc-800' : 'divide-ds-zinc-200')} data-testid="mcp-audit-list">
          {entries.map((entry) => {
            const successful = entry.status === 'success';
            const expanded = expandedId === entry.id;
            const formattedTime = entry.created_at ? new Date(entry.created_at).toLocaleString(locale) : '—';
            return (
              <div key={entry.id} data-testid="mcp-audit-row">
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setExpandedId(expanded ? null : entry.id)}
                  className={cn('flex w-full items-center gap-2 px-3 py-2 text-left text-[10px] transition-colors', dark ? 'hover:bg-ds-zinc-900/60' : 'hover:bg-ds-zinc-100/70')}
                >
                  <ChevronDown className={cn('w-3 h-3 shrink-0 text-ds-zinc-500 transition-transform', !expanded && '-rotate-90')} />
                  <span className={cn(
                    'shrink-0 rounded border px-1.5 py-0.5 font-bold uppercase leading-none',
                    successful ? 'bg-ds-emerald-500/10 text-ds-emerald-455 border-ds-emerald-500/20' : 'bg-ds-rose-500/10 text-ds-rose-455 border-ds-rose-500/20',
                  )}>
                    {successful ? t('settings.mcpAudit.success') : t('settings.mcpAudit.error')}
                  </span>
                  <span className={cn('min-w-0 truncate font-mono font-bold', dark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>{entry.tool_name}</span>
                  <span className={cn('hidden shrink-0 sm:inline', muted)}>{entry.server_name}</span>
                  <span className={cn('ml-auto shrink-0 tabular-nums', muted)}>{formattedTime}</span>
                </button>
                {expanded && (
                  <div className="space-y-2 px-3 pb-3 pl-8">
                    <div className={cn('flex flex-wrap gap-x-3 gap-y-1 text-[10px]', muted)}>
                      <span>{t('settings.mcpAudit.server', { server: entry.server_name })}</span>
                      <span>{t('settings.mcpAudit.user', { user: entry.user_name || '—' })}</span>
                      <span>{t('settings.mcpAudit.duration', { duration: entry.duration_ms ?? 0 })}</span>
                      {entry.project_name && <span>{t('settings.mcpAudit.project', { project: entry.project_name })}</span>}
                      {entry.trace_id && <span className="font-mono">trace: {entry.trace_id}</span>}
                    </div>
                    <pre className={cn(
                      'max-h-40 overflow-auto rounded border p-2 text-[10px] leading-relaxed whitespace-pre-wrap break-all',
                      dark ? 'bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-400' : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-600',
                    )}>
                      {JSON.stringify(entry.arguments ?? {}, null, 2)}
                    </pre>
                    {entry.error_message && <p className="text-[10px] text-ds-rose-500 break-all">{entry.error_message}</p>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {total > 0 && (
        <div className="flex items-center justify-between gap-3 text-[10px]">
          <span className={muted} data-testid="mcp-audit-range">{t('settings.mcpAudit.range', { from, to, total })}</span>
          <div className="flex items-center gap-1.5">
            <Button type="button" size="sm" variant="outline" disabled={page === 0 || loading} onClick={() => { setPage(page - 1); setExpandedId(null); }}
              aria-label={t('settings.mcpAudit.previousPage')} className={cn('h-7 w-7 p-0 focus:ring-0', control)}>
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <span className={cn('tabular-nums', muted)}>{t('settings.mcpAudit.pageOf', { page: page + 1, pages: pageCount })}</span>
            <Button type="button" size="sm" variant="outline" disabled={page + 1 >= pageCount || loading} onClick={() => { setPage(page + 1); setExpandedId(null); }}
              aria-label={t('settings.mcpAudit.nextPage')} className={cn('h-7 w-7 p-0 focus:ring-0', control)}>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
