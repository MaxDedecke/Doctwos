"use client";

import { api } from '@/app/services/api';
import { KnowledgeNodeIcon } from '@/components/KnowledgeNodeIcon';
import type { AgentSearchViewAction, KnowledgeSource, Project, SearchResult } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { AlertCircle, Loader2, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

interface AgentSearchResultsViewProps {
  target: AgentSearchViewAction['target'] | null | undefined;
  selectedProject: Project | null;
  connectedSources: KnowledgeSource[];
  theme: string;
  onSelectResult: (result: SearchResult) => void | Promise<void>;
}

export function AgentSearchResultsView({ target, selectedProject, connectedSources, theme, onSelectResult }: AgentSearchResultsViewProps) {
  const { t } = useLanguage();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!target) {
      setResults([]);
      setCounts({});
      setError(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    api.searchGlobal(target.query, {
      types: target.types.join(','),
      projectId: target.project_id,
      sourceId: target.source_id ?? undefined,
      limit: target.limit,
      signal: controller.signal,
    }).then(response => {
      setResults(Array.isArray(response.data.results) ? response.data.results : []);
      setCounts(response.data.counts || {});
    }).catch((cause: unknown) => {
      if (cause && typeof cause === 'object' && 'name' in cause && cause.name === 'CanceledError') return;
      setResults([]);
      setCounts({});
      setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [target]);

  if (!target) {
    return <div className="h-full flex items-center justify-center text-xs text-ds-zinc-500">{t('agentSearchView.noSearch')}</div>;
  }

  const hasMore = target.types.some(type => (counts[type] || 0) > results.filter(item => item.node_type === type).length);
  const scopeLabel = target.source_id !== null
    ? t('agentSearchView.sourceScope', {
      source: connectedSources.find(source => Number(source.id) === target.source_id)?.name || target.source_id,
    })
    : selectedProject?.id === target.project_id
      ? selectedProject.name
      : t('agentSearchView.projectScope', { project: target.project_id });

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className={cn(
        'px-3 py-2 border-b shrink-0',
        theme === 'dark' ? 'border-ds-zinc-800 bg-ds-zinc-950/40' : 'border-ds-zinc-200 bg-ds-zinc-50/70',
      )}>
        <div className="flex items-center gap-2 min-w-0">
          <Search className="w-3.5 h-3.5 shrink-0 text-ds-indigo-400" />
          <span className="text-xs font-semibold truncate" title={target.query}>{target.query}</span>
        </div>
        <div className="mt-1 pl-5 text-[10px] text-ds-zinc-500 truncate">
          {scopeLabel} · {target.types.map(type => t(`agentSearchView.types.${type}`)).join(', ')}
        </div>
        {!loading && !error && (
          <div className="mt-1 pl-5 text-[10px] text-ds-zinc-500">
            {t('agentSearchView.summary', { count: results.length })}
            {target.types.map(type => ` · ${t(`agentSearchView.types.${type}`)}: ${counts[type] || 0}`).join('')}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading && (
          <div className="h-full min-h-32 flex items-center justify-center gap-2 text-xs text-ds-zinc-500">
            <Loader2 className="w-4 h-4 animate-spin" /> {t('agentSearchView.loading')}
          </div>
        )}
        {!loading && error && (
          <div role="alert" className="m-4 flex items-start gap-2 rounded-md border border-ds-red-500/30 bg-ds-red-500/5 p-3 text-xs text-ds-red-400">
            <AlertCircle className="w-4 h-4 shrink-0" /> {t('agentSearchView.loadError')}
          </div>
        )}
        {!loading && !error && results.length === 0 && (
          <div className="h-full min-h-32 flex items-center justify-center px-4 text-center text-xs text-ds-zinc-500">
            {t('agentSearchView.empty', { query: target.query })}
          </div>
        )}
        {!loading && !error && results.length > 0 && (
          <div className="divide-y divide-ds-zinc-800/50">
            {results.map(result => {
              const path = result.node_meta?.file_path;
              return (
                <button
                  type="button"
                  key={`${result.node_type}-${result.node_id}`}
                  onClick={() => void onSelectResult(result)}
                  className={cn(
                    'w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-colors',
                    theme === 'dark' ? 'hover:bg-ds-zinc-800/60' : 'hover:bg-ds-zinc-100',
                  )}
                >
                  <KnowledgeNodeIcon
                    node={{ node_type: result.node_type, node_url: result.node_url, node_meta: result.node_meta }}
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ds-indigo-400"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">{result.node_label}</span>
                    {path && <span className="mt-0.5 block truncate font-mono text-[10px] text-ds-zinc-500">{path}</span>}
                  </span>
                  <span className="shrink-0 pt-0.5 text-[9px] uppercase tracking-wide text-ds-zinc-500">
                    {t(`agentSearchView.types.${result.node_type}`)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        {!loading && !error && hasMore && (
          <p className="px-3 py-2 text-[10px] text-ds-amber-500">
            {t('agentSearchView.truncated', { count: target.types.reduce((sum, type) => sum + Math.max(0, (counts[type] || 0) - results.filter(item => item.node_type === type).length), 0) })}
          </p>
        )}
      </div>
    </div>
  );
}
