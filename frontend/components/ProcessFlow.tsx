"use client";
import type { CodeEntity } from '@/types/domain';

import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { buildFlowRows, nextExpansion, type DataVerb, type FlowProjection, type FlowRow, type PathEntry } from '@/lib/processFlow';
import { cn } from '@/lib/utils';
import { AlertTriangle, ChevronRight, Database, ExternalLink, FileCode, GitBranch, Loader2, RefreshCw, Repeat, Route, Split, Square, Workflow } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

interface Props {
  theme: string;
  focusedEntity: Pick<CodeEntity, 'id' | 'name'> | null;
  projectId?: number | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
}

type Gate = { truncated: boolean };
// Grenzen von „Alles aufklappen“: Java-Aufrufe können über den halben Bestand führen.
const EXPAND_ALL_MAX_DEPTH = 6;
const EXPAND_ALL_MAX_REQUESTS = 150;
const EXPAND_ALL_PARALLEL = 6;
const VERB_ORDER: DataVerb[] = ['read', 'write', 'use'];

async function fetchProjection(entityId: number, projectId: number | null | undefined): Promise<{ projection: FlowProjection; truncated: boolean }> {
  const projectParam = projectId ? `&project_id=${projectId}` : '';
  const response = await api.fetch(`${API_URL}/process/focus?entity_id=${entityId}&hops=1&direction=outgoing&node_limit=500&edge_limit=1000&flow_view=true${projectParam}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data: FlowProjection & { root_node_id?: string; truncation?: { truncated: boolean } } = await response.json();
  return {
    projection: { nodes: data.nodes || [], transitions: data.transitions || [], rootNodeId: data.root_node_id },
    truncated: Boolean(data.truncation?.truncated),
  };
}

type Caller = { id: string; label: string; filePath: string; line: number; sourceId?: number | null };

async function fetchCallers(entityId: number, projectId: number | null | undefined): Promise<Caller[]> {
  const projectParam = projectId ? `&project_id=${projectId}` : '';
  const response = await api.fetch(`${API_URL}/process/focus?entity_id=${entityId}&hops=1&direction=incoming&kinds=call,jump,iteration&node_limit=200&edge_limit=200${projectParam}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data: FlowProjection & { root_node_id: string } = await response.json();
  const labels = new Map(data.nodes.map(node => [node.id, node.label]));
  return data.transitions
    .filter(transition => transition.target === data.root_node_id)
    .sort((a, b) => a.locator.file_path.localeCompare(b.locator.file_path) || a.locator.start_line - b.locator.start_line)
    .map(transition => ({
      id: transition.id,
      label: labels.get(transition.source) ?? '?',
      filePath: transition.locator.file_path,
      line: transition.locator.start_line,
      sourceId: transition.locator.source_id,
    }));
}

type SharedUser = {
  program: string; entity_id: number; access: 'read' | 'write' | 'use'; via: 'batch' | 'cics' | 'sql' | 'resource';
  jobs: string[]; is_focus: boolean; certainty: 'certain' | 'possible'; file_path: string; line: number;
};
type SharedResource = { key: string; label: string; kind: string; shared: boolean; users: SharedUser[] };

async function fetchSharedData(entityId: number, projectId: number | null | undefined): Promise<SharedResource[]> {
  const projectParam = projectId ? `&project_id=${projectId}` : '';
  const response = await api.fetch(`${API_URL}/process/shared-data?entity_id=${entityId}${projectParam}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()).resources;
}

export function ProcessFlow({ theme, focusedEntity: focusFromView, projectId, onFileSelect }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  // „Ablauf öffnen“ aus den gemeinsamen Dateien: bleibt hier, bis die Ansicht einen neuen Fokus setzt.
  const [followed, setFollowed] = useState<{ from: number | null; entity: Pick<CodeEntity, 'id' | 'name'> } | null>(null);
  const focusId = focusFromView?.id ?? null;
  if (followed && followed.from !== focusId) setFollowed(null);
  const focusedEntity = followed && followed.from === focusId ? followed.entity : focusFromView;
  const rootEntityId = focusedEntity?.id ?? null;
  const rootId = rootEntityId != null ? `entity:${rootEntityId}` : null;

  const [projections, setProjections] = useState<Map<string, FlowProjection>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [openData, setOpenData] = useState<Set<string>>(new Set());
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate>({ truncated: false });
  const [callers, setCallers] = useState<Caller[] | 'loading' | null>(null);
  const [sharedData, setSharedData] = useState<SharedResource[] | 'loading' | null>(null);
  const [expandingAll, setExpandingAll] = useState(false);
  const [expandLimited, setExpandLimited] = useState(false);
  const requested = useRef<Set<string>>(new Set());
  const generation = useRef(0);

  const load = useCallback(async (nodeId: string, entityId: number, force = false) => {
    if (!force && requested.current.has(nodeId)) return;
    requested.current.add(nodeId);
    const current = generation.current;
    setLoadingIds(previous => new Set(previous).add(nodeId));
    try {
      const { projection, truncated } = await fetchProjection(entityId, projectId);
      if (generation.current !== current) return;
      setProjections(previous => new Map(previous).set(nodeId, projection));
      if (truncated) setGate({ truncated: true });
      setError(null);
    } catch (err) {
      if (generation.current !== current) return;
      requested.current.delete(nodeId);
      setError((err instanceof Error ? err.message : undefined) || t('processFlow.loadError'));
    } finally {
      if (generation.current === current) {
        setLoadingIds(previous => { const next = new Set(previous); next.delete(nodeId); return next; });
      }
    }
  }, [projectId, t]);

  // Neuer Einstieg oder anderes Projekt: alles verwerfen und die Wurzel laden.
  useEffect(() => {
    generation.current += 1;
    requested.current = new Set();
    queueMicrotask(() => {
      setProjections(new Map());
      setExpanded(new Set());
      setOpenData(new Set());
      setSelectedKey(null);
      setLoadingIds(new Set());
      setGate({ truncated: false });
      setError(null);
      setExpandingAll(false);
      setExpandLimited(false);
      setCallers(null);
      setSharedData(null);
      if (rootEntityId != null) load(`entity:${rootEntityId}`, rootEntityId);
    });
    // load hängt nur an projectId/t; ein Sprachwechsel soll nicht neu laden.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootEntityId, projectId]);

  const [hideHelpers, setHideHelpers] = useState(true);
  const [hideData, setHideData] = useState(true);
  const { rows, capped, hiddenHelpers, hiddenData } = useMemo(() => {
    if (!rootId) return { rows: [], capped: false, hiddenHelpers: 0, hiddenData: 0 };
    const built = buildFlowRows(rootId, projections, expanded, { hideHelpers, hideData });
    // Besteht ein Schritt nur aus Datenzugriffen, sind sie sein Inhalt und bleiben sichtbar.
    return built.rows.length <= 1 && built.hiddenData > 0
      ? buildFlowRows(rootId, projections, expanded, { hideHelpers })
      : built;
  }, [rootId, projections, expanded, hideHelpers, hideData]);

  const toggleStep = (row: FlowRow) => {
    if (!row.expandable) return;
    setExpanded(previous => {
      const next = new Set(previous);
      if (next.has(row.key)) next.delete(row.key); else next.add(row.key);
      return next;
    });
    if (!row.expanded && row.nodeId && row.entityId != null) load(row.nodeId, row.entityId);
  };

  const toggleCallers = async () => {
    if (callers !== null || rootEntityId == null) { setCallers(null); return; }
    const current = generation.current;
    setCallers('loading');
    try {
      const found = await fetchCallers(rootEntityId, projectId);
      if (generation.current === current) setCallers(found);
    } catch (err) {
      if (generation.current !== current) return;
      setCallers(null);
      setError((err instanceof Error ? err.message : undefined) || t('processFlow.loadError'));
    }
  };

  const toggleSharedData = async () => {
    if (sharedData !== null || rootEntityId == null) { setSharedData(null); return; }
    const current = generation.current;
    setSharedData('loading');
    try {
      const found = await fetchSharedData(rootEntityId, projectId);
      if (generation.current === current) setSharedData(found);
    } catch (err) {
      if (generation.current !== current) return;
      setSharedData(null);
      setError((err instanceof Error ? err.message : undefined) || t('processFlow.loadError'));
    }
  };

  const expandAll = async () => {
    if (!rootId || expandingAll) return;
    const current = generation.current;
    setExpandingAll(true);
    setExpandLimited(false);
    const openKeys = new Set(expanded);
    const loaded = new Map(projections);
    let requests = 0;
    let limited = false;
    try {
      for (let depth = 0; depth < EXPAND_ALL_MAX_DEPTH; depth += 1) {
        const built = buildFlowRows(rootId, loaded, openKeys, { hideHelpers });
        const next = nextExpansion(built.rows);
        if (next.length === 0) break;
        if (built.capped) { limited = true; break; }
        const missing = next.filter(row => !loaded.has(row.nodeId!));
        if (requests + missing.length > EXPAND_ALL_MAX_REQUESTS) { limited = true; break; }
        requests += missing.length;
        for (let start = 0; start < missing.length; start += EXPAND_ALL_PARALLEL) {
          const batch = missing.slice(start, start + EXPAND_ALL_PARALLEL);
          const results = await Promise.all(batch.map(row => fetchProjection(row.entityId!, projectId)));
          if (generation.current !== current) return;
          results.forEach(({ projection, truncated }, index) => {
            loaded.set(batch[index].nodeId!, projection);
            requested.current.add(batch[index].nodeId!);
            if (truncated) setGate({ truncated: true });
          });
        }
        next.forEach(row => openKeys.add(row.key));
        setProjections(new Map(loaded));
        setExpanded(new Set(openKeys));
        if (depth === EXPAND_ALL_MAX_DEPTH - 1 && nextExpansion(buildFlowRows(rootId, loaded, openKeys, { hideHelpers }).rows).length > 0) limited = true;
      }
      setExpandLimited(limited);
    } catch (err) {
      if (generation.current === current) setError((err instanceof Error ? err.message : undefined) || t('processFlow.loadError'));
    } finally {
      if (generation.current === current) setExpandingAll(false);
    }
  };

  const toggleData = (key: string) => setOpenData(previous => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const toggleSelect = (row: FlowRow) => setSelectedKey(previous => (previous === row.key ? null : row.key));

  // Der Lauf eines Schritts: alle Vorfahren (von oben), er selbst und alles darunter (nach unten).
  const inRun = (key: string) => selectedKey != null && (key === selectedKey || selectedKey.startsWith(`${key}/`) || key.startsWith(`${selectedKey}/`));

  const open = (row: { filePath: string; line: number; sourceId?: number | null }) => {
    if (row.filePath && row.filePath !== '<unknown>') onFileSelect(row.filePath, row.line, row.sourceId);
  };

  if (!focusedEntity || rootEntityId == null) {
    return <div className="h-full flex flex-col items-center justify-center gap-2 text-ds-zinc-500"><FileCode className="w-10 h-10 opacity-30" /><p className="text-sm">{t('callGraphView.focusFirst')}</p></div>;
  }

  const rootLoaded = projections.has(`entity:${rootEntityId}`);

  return (
    <div className={cn('h-full flex flex-col', isDark ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
      <div className={cn('px-3 py-2 border-b flex flex-wrap items-center gap-2', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
        <div className="min-w-0 mr-auto">
          <div className="text-xs font-bold truncate">{focusedEntity.name}</div>
          {followed && focusFromView && (
            <button type="button" onClick={() => setFollowed(null)} className="block text-[0.625rem] text-ds-indigo-400 hover:underline">
              ← {t('processFlow.backTo', { name: focusFromView.name })}
            </button>
          )}
          <div className="text-[0.5625rem] uppercase tracking-wider text-ds-zinc-500">{t('processFlow.subtitle')}</div>
        </div>
        <button
          type="button"
          onClick={() => void toggleCallers()}
          aria-expanded={callers !== null}
          title={t('processFlow.callersTitle')}
          className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors"
        >
          {t('processFlow.callers')}
        </button>
        <button
          type="button"
          onClick={() => void toggleSharedData()}
          aria-expanded={sharedData !== null}
          title={t('processFlow.sharedDataTitle')}
          className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors"
        >
          {t('processFlow.sharedData')}
        </button>
        {(hiddenData > 0 || !hideData) && (
          <button
            type="button"
            aria-pressed={hideData}
            onClick={() => setHideData(value => !value)}
            className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors"
          >
            {hideData ? t('processFlow.dataHidden', { count: hiddenData }) : t('processFlow.dataShown')}
          </button>
        )}
        {(hiddenHelpers > 0 || !hideHelpers) && (
          <button
            type="button"
            aria-pressed={hideHelpers}
            title={t('processFlow.helpersTitle')}
            onClick={() => setHideHelpers(value => !value)}
            className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors"
          >
            {hideHelpers ? t('processFlow.helpersHidden', { count: hiddenHelpers }) : t('processFlow.helpersShown')}
          </button>
        )}
        <button
          type="button"
          onClick={() => void expandAll()}
          disabled={expandingAll}
          title={t('processFlow.expandAllTitle')}
          className="flex h-7 items-center gap-1 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors disabled:opacity-60"
        >
          {expandingAll && <Loader2 className="h-3 w-3 animate-spin" />}
          {t('processFlow.expandAll')}
        </button>
        <button
          type="button"
          onClick={() => { setExpanded(new Set()); setExpandLimited(false); }}
          className="h-7 px-2 rounded border border-ds-zinc-700 hover:border-ds-indigo-500 text-[0.625rem] font-bold text-ds-zinc-400 hover:text-ds-indigo-400 transition-colors"
        >
          {t('processFlow.collapseAll')}
        </button>
        <button
          type="button"
          title={t('callGraphView.reloadTitle')}
          aria-label={t('callGraphView.reloadTitle')}
          onClick={() => {
            generation.current += 1;
            requested.current = new Set();
            setProjections(new Map());
            setGate({ truncated: false });
            if (rootEntityId != null) load(`entity:${rootEntityId}`, rootEntityId, true);
          }}
          className="p-1.5 text-ds-zinc-500 hover:text-ds-indigo-400"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', loadingIds.size > 0 && 'animate-spin')} />
        </button>
      </div>

      {(gate.truncated || capped || error || expandLimited) && (
        <div className="px-3 py-1.5 flex flex-wrap gap-2 text-[0.625rem]">
          {error && <span className="rounded border border-ds-red-500/30 bg-ds-red-500/10 px-2 py-1 text-ds-red-400">{error}</span>}
          {(gate.truncated || capped) && (
            <span className="flex items-center gap-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 px-2 py-1 text-ds-amber-400">
              <AlertTriangle className="w-3 h-3" />{capped ? t('processFlow.capped') : t('processFlow.truncated')}
            </span>
          )}
          {expandLimited && !capped && (
            <span className="flex items-center gap-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 px-2 py-1 text-ds-amber-400">
              <AlertTriangle className="w-3 h-3" />{t('processFlow.expandLimited')}
            </span>
          )}
        </div>
      )}

      {callers !== null && (
        <div className={cn('shrink-0 border-b px-3 py-2 text-[0.6875rem]', isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200')}>
          {callers === 'loading' && <Loader2 className="h-3 w-3 animate-spin text-ds-indigo-500" />}
          {callers !== 'loading' && callers.length === 0 && <span className="text-ds-zinc-500">{t('processFlow.noCallers')}</span>}
          {callers !== 'loading' && callers.length > 0 && (
            <ul className="max-h-40 space-y-0.5 overflow-y-auto">
              {callers.map(caller => (
                <li key={caller.id}>
                  <button type="button" onClick={() => open(caller)} className="flex max-w-full items-center gap-2 text-left hover:text-ds-indigo-400">
                    <span className="truncate font-semibold">{caller.label}</span>
                    <span className="shrink-0 font-mono text-[0.625rem] text-ds-zinc-500">{caller.filePath.split('/').pop()}:{caller.line}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {sharedData !== null && (
        <SharedDataPanel
          data={sharedData}
          isDark={isDark}
          t={t}
          onOpenSource={user => open({ filePath: user.file_path, line: user.line })}
          onFollow={user => setFollowed({ from: focusId, entity: { id: user.entity_id, name: user.program } })}
        />
      )}

      {/* Legende der Markierungen auf dem Zeitstrahl */}
      <div className={cn('flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b px-3 py-1.5 text-[0.625rem] uppercase tracking-[0.12em]', isDark ? 'border-ds-zinc-800 bg-ds-zinc-900/40 text-ds-zinc-400' : 'border-ds-zinc-200 bg-ds-zinc-50 text-ds-zinc-500')}>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-ds-indigo-500" /><Workflow className="h-3 w-3" />{t('processFlow.laneControl')}</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-ds-cyan-500" /><Database className="h-3 w-3" />{t('processFlow.laneData')}</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-dashed border-ds-amber-500" /><GitBranch className="h-3 w-3" />{t('processFlow.laneExternal')}</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rotate-45 bg-ds-amber-500" /><Split className="h-3 w-3" />{t('processFlow.laneGuard')}</span>
        <span className="ml-auto normal-case tracking-normal">{t('processFlow.line')} ↓</span>
      </div>

      <div className="relative flex-1 min-h-0 overflow-y-auto px-3 py-3" role="table" aria-label={t('processFlow.subtitle')}>
        {!rootLoaded && loadingIds.size > 0 && (
          <div className="flex items-center justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-ds-indigo-500" /></div>
        )}
        {rootLoaded && rows.length <= 1 && (
          <div className="py-10 text-center text-xs text-ds-zinc-500">{t('processFlow.empty')}</div>
        )}
        {rows.map((row, index) => {
          const isFirst = index === 0;
          const isLast = index === rows.length - 1;
          const isGuard = row.lane === 'control' && Boolean(row.guard);
          const isLoopGuard = isGuard && row.guard?.type === 'LOOP';
          const indentRem = Math.max(0, row.indent - 1) * 1.1;
          const lit = inRun(row.key);
          const dim = selectedKey != null && !lit;
          return (
            <div key={row.key} role="row" className={cn('group/step flex gap-2 transition-opacity', dim && 'opacity-35')}>
              {/* Zeilennummer im Quelltext: die Zeitachse */}
              <div className="w-11 shrink-0 pt-1.5 text-right">
                {row.line > 0 && (
                  <button
                    type="button"
                    onClick={() => open(row)}
                    title={t('processFlow.openSource')}
                    className="font-mono text-[0.625rem] tabular-nums text-ds-zinc-500 hover:text-ds-indigo-400"
                  >
                    {row.line}
                  </button>
                )}
              </div>

              {/* Zeitstrahl: durchgehende Linie mit Marker je Schritt */}
              <div className="relative w-5 shrink-0" aria-hidden="true">
                <span className={cn('absolute left-1/2 w-0.5 -translate-x-1/2', lit ? 'bg-ds-indigo-500' : isDark ? 'bg-ds-zinc-700' : 'bg-ds-zinc-300', isFirst ? 'top-3.5' : 'top-0', isLast ? 'h-3.5' : 'bottom-0')} />
                <TimelineMarker row={row} isGuard={isGuard} isLoop={isLoopGuard} isDark={isDark} />
              </div>

              <div className={cn('min-w-0 flex-1 pb-2.5', row.lane === 'data' && 'pt-0.5')}>
                {row.lane === 'control' && row.guard && <GuardPill entry={{ ...row.guard, dataCount: row.dataCount }} isDark={isDark} indent={row.indent} t={t} />}
                {row.lane === 'control' && !row.guard && <StepPill row={row} isDark={isDark} selected={selectedKey === row.key} onToggle={toggleStep} onSelect={toggleSelect} onOpen={open} loading={row.nodeId ? loadingIds.has(row.nodeId) : false} t={t} />}
                {row.lane === 'data' && (
                  <div style={{ paddingLeft: `${indentRem + 1.25}rem` }}>
                    <DataCard row={row} isDark={isDark} isOpen={openData.has(row.key)} onToggle={() => toggleData(row.key)} onOpen={open} t={t} />
                  </div>
                )}
                {row.lane === 'external' && <StepPill row={row} isDark={isDark} selected={selectedKey === row.key} onToggle={toggleStep} onSelect={toggleSelect} onOpen={open} loading={false} t={t} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SharedDataPanel({ data, isDark, t, onOpenSource, onFollow }: {
  data: SharedResource[] | 'loading'; isDark: boolean; t: Translate;
  onOpenSource: (user: SharedUser) => void;
  onFollow: (user: SharedUser) => void;
}) {
  const border = isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200';
  if (data === 'loading') return <div className={cn('shrink-0 border-b px-3 py-2', border)}><Loader2 className="h-3 w-3 animate-spin text-ds-indigo-500" /></div>;
  const shared = data.filter(resource => resource.shared);
  const alone = data.length - shared.length;
  return (
    <div className={cn('max-h-64 shrink-0 space-y-2 overflow-y-auto border-b px-3 py-2 text-[0.6875rem]', border)}>
      {shared.length === 0 && <p className="text-ds-zinc-500">{t('processFlow.sharedDataEmpty')}</p>}
      {shared.map(resource => (
        <div key={resource.key}>
          <div className="flex min-w-0 items-center gap-1.5 font-semibold">
            <Database className="h-3 w-3 shrink-0 text-ds-cyan-500" />
            <span className="truncate font-mono" title={resource.label}>{resource.label}</span>
          </div>
          <ul className="mt-0.5 space-y-0.5 pl-[1.125rem]">
            {resource.users.map(user => (
              <li key={`${user.entity_id}:${user.access}`} className="flex min-w-0 flex-wrap items-center gap-x-1.5">
                <span className={cn('w-14 shrink-0', user.access === 'write' ? 'text-ds-amber-500' : 'text-ds-zinc-500')}>{t(`processFlow.verbs.${user.access}`)}</span>
                {user.is_focus
                  ? <span className="font-semibold">{user.program}</span>
                  : <button type="button" onClick={() => onFollow(user)} title={t('processFlow.followProgram')} className="font-semibold text-ds-indigo-400 hover:underline">{user.program}</button>}
                <span className="text-ds-zinc-500">{user.via === 'resource' ? '' : user.via === 'cics' ? t('processFlow.viaDialog') : user.via === 'sql' ? 'SQL' : user.jobs.length ? t('processFlow.viaJob', { names: user.jobs.join(', ') }) : t('processFlow.viaBatch')}</span>
                {user.certainty === 'possible' && <Badge tone="slate">{t('processFlow.possible')}</Badge>}
                <button type="button" onClick={() => onOpenSource(user)} className="font-mono text-[0.625rem] text-ds-zinc-500 hover:text-ds-indigo-400">{user.file_path.split('/').pop()}:{user.line}</button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {alone > 0 && <p className="text-ds-zinc-500">{t('processFlow.sharedDataAlone', { count: alone })}</p>}
    </div>
  );
}

function TimelineMarker({ row, isGuard, isLoop, isDark }: { row: FlowRow; isGuard: boolean; isLoop: boolean; isDark: boolean }) {
  const page = isDark ? 'bg-ds-zinc-950' : 'bg-ds-white';
  const base = 'absolute left-1/2 top-1.5 z-10 -translate-x-1/2';
  if (row.key === 'root') {
    return <span className={cn(base, 'h-3.5 w-3.5 rounded-full border-2 border-ds-indigo-500 bg-ds-indigo-500 ring-4 ring-ds-indigo-500/20')} />;
  }
  if (isGuard) {
    return isLoop
      ? <span className={cn(base, 'h-3 w-3 rounded-full border-2 border-ds-indigo-400', page)} />
      : <span className={cn(base, 'top-2 h-2.5 w-2.5 rotate-45 bg-ds-amber-500')} />;
  }
  if (row.lane === 'data') return <span className={cn(base, 'top-2 h-2.5 w-2.5 rounded-sm bg-ds-cyan-500')} />;
  if (row.lane === 'external') return <span className={cn(base, 'h-3 w-3 rounded-full border-2 border-dashed border-ds-amber-500', page)} />;
  return <span className={cn(base, 'h-3 w-3 rounded-full border-2', row.certainty === 'certain' ? 'border-ds-indigo-500' : 'border-dashed border-ds-zinc-500', page)} />;
}

type Translate = (key: string, vars?: Record<string, string | number>) => string;

function StepPill({ row, isDark, selected, onToggle, onSelect, onOpen, loading, t }: {
  row: FlowRow; isDark: boolean; selected: boolean; loading: boolean; t: Translate;
  onToggle: (row: FlowRow) => void;
  onSelect: (row: FlowRow) => void;
  onOpen: (row: { filePath: string; line: number; sourceId?: number | null }) => void;
}) {
  const isRoot = row.key === 'root';
  const external = row.lane === 'external';
  const dashed = row.certainty !== 'certain' || external;
  return (
    <div className="flex min-w-0 items-start gap-1" style={{ paddingLeft: row.lane === 'control' ? `${Math.max(0, row.indent - 1) * 1.1}rem` : undefined }}>
      {row.expandable ? (
        <button
          type="button"
          onClick={() => onToggle(row)}
          aria-expanded={row.expanded}
          aria-label={t(row.expanded ? 'processFlow.collapse' : 'processFlow.expand', { name: row.label })}
          className="mt-0.5 shrink-0 rounded p-0.5 text-ds-zinc-500 hover:text-ds-indigo-400"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <ChevronRight className={cn('h-3 w-3 transition-transform duration-150', row.expanded && 'rotate-90')} />}
        </button>
      ) : <span className="w-4 shrink-0" />}
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-1">
        <button
          type="button"
          onClick={() => onSelect(row)}
          aria-pressed={selected}
          title={row.label}
          className={cn(
            'max-w-full truncate rounded-md border px-2.5 py-1 text-left text-xs font-semibold shadow-sm transition-colors',
            selected && 'ring-2 ring-ds-indigo-500/60',
            dashed && 'border-dashed',
            isRoot
              ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400'
              : external
                ? (isDark ? 'border-ds-amber-500/60 text-ds-amber-400 hover:bg-ds-amber-500/10' : 'border-ds-amber-500/70 text-ds-amber-700 hover:bg-ds-amber-500/10')
                : (isDark ? 'border-ds-blue-400/50 bg-ds-blue-400/20 text-ds-zinc-50 hover:border-ds-indigo-500' : 'border-ds-blue-500/40 bg-ds-blue-500/10 text-ds-zinc-900 hover:border-ds-indigo-500'),
          )}
        >
          {row.label}
        </button>
        <span className="flex shrink-0 items-center opacity-0 transition-opacity group-hover/step:opacity-100 focus-within:opacity-100">
          <button type="button" onClick={() => onSelect(row)} title={t('processFlow.highlightRun')} aria-label={t('processFlow.highlightRun')} className="rounded p-1 text-ds-zinc-500 hover:text-ds-indigo-400">
            <Route className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => onOpen(row)} title={t('processFlow.openSource')} aria-label={t('processFlow.openSource')} className="rounded p-1 text-ds-zinc-500 hover:text-ds-indigo-400">
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        </span>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1 empty:hidden">
          {row.cycle && (
            <Badge tone="amber"><Repeat className="h-2.5 w-2.5" />{t(row.cycle === 'recursion' ? 'processFlow.recursion' : 'processFlow.cycle')}</Badge>
          )}
          {row.loop && (
            <Badge tone="indigo"><Repeat className="h-2.5 w-2.5" />{guardLabel({ type: 'LOOP', kind: row.loop.kind, text: row.loop.text }, t)}</Badge>
          )}
          {row.fallThrough && <Badge tone="indigo">{t('processFlow.fallThrough')}</Badge>}
          {row.thru && <Badge tone="slate">{t('processFlow.thru', { name: row.thru })}</Badge>}
          {row.openElsewhere && <Badge tone="slate">{t('processFlow.openElsewhere')}</Badge>}
          {row.transitionKind === 'jump' && <Badge tone="slate">GOTO</Badge>}
          {row.transitionKind === 'exit' && <Badge tone="slate"><Square className="h-2.5 w-2.5" />{t('processFlow.exit')}</Badge>}
          {row.invocationKind === 'cics_xctl' && <Badge tone="indigo">{t('processFlow.transferNoReturn')}</Badge>}
          {row.invocationKind === 'cics_link' && <Badge tone="indigo">{t('processFlow.link')}</Badge>}
          {row.candidateTargets && row.candidateTargets.length > 0 && (
            <Badge tone="slate"><span className="max-w-[16rem] truncate" title={row.candidateTargets.join(', ')}>{t('processFlow.candidates', { names: row.candidateTargets.join(', ') })}</span></Badge>
          )}
          {row.transitionKind === 'branch' && <Badge tone="amber"><GitBranch className="h-2.5 w-2.5" />{t('processFlow.multiTarget')}</Badge>}
          {row.certainty === 'possible' && <Badge tone="slate">{t('processFlow.possible')}</Badge>}
          {row.certainty === 'unresolved' && <Badge tone="amber">{t('processFlow.unresolved')}</Badge>}
          {row.condition && <Badge tone="slate"><span className="max-w-[16rem] truncate" title={row.condition}>{t('processFlow.condition')}: {row.condition}</span></Badge>}
        </div>
      </div>
    </div>
  );
}

function DataCard({ row, isDark, isOpen, onToggle, onOpen, t }: {
  row: FlowRow; isDark: boolean; isOpen: boolean; t: Translate; onToggle: () => void;
  onOpen: (row: { filePath: string; line: number; sourceId?: number | null }) => void;
}) {
  const counts = row.counts!;
  const targets = row.targets ?? [];
  const shown = targets.slice(0, 3);
  return (
    <div className={cn('rounded-md border px-2 py-1 text-[0.625rem]', isDark ? 'border-ds-blue-400/40 bg-ds-blue-400/15' : 'border-ds-blue-500/40 bg-ds-blue-500/10')}>
      <button type="button" onClick={onToggle} aria-expanded={isOpen} className="flex w-full items-center gap-1 text-left">
        <ChevronRight className={cn('h-3 w-3 shrink-0 text-ds-zinc-500 transition-transform duration-150', isOpen && 'rotate-90')} />
        <span className="font-semibold">
          {VERB_ORDER.filter(verb => counts[verb] > 0).map(verb => `${counts[verb]}× ${t(`processFlow.verbs.${verb}`)}`).join(' · ')}
        </span>
      </button>
      {!isOpen && shown.length > 0 && (
        <div className="mt-0.5 truncate pl-4 font-mono text-ds-zinc-500" title={targets.join(', ')}>
          {shown.join(', ')}{targets.length > shown.length ? ` +${targets.length - shown.length}` : ''}
        </div>
      )}
      {isOpen && (
        <ul className="mt-1 space-y-0.5 pl-4">
          {row.accesses!.map(access => (
            <li key={access.id} className="flex items-center gap-1.5">
              <span className="w-14 shrink-0 text-ds-zinc-500">{t(`processFlow.verbs.${access.verb}`)}</span>
              <button type="button" onClick={() => onOpen(access)} className="min-w-0 truncate font-mono hover:text-ds-indigo-400" title={access.target}>{access.target}</button>
              <span className="ml-auto shrink-0 tabular-nums text-ds-zinc-500">{access.line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Badge({ tone, children }: { tone: 'amber' | 'slate' | 'indigo'; children: React.ReactNode }) {
  return (
    <span className={cn(
      'inline-flex items-center gap-0.5 rounded border px-1 py-px text-[0.5625rem] font-semibold',
      tone === 'amber' ? 'border-ds-amber-500/40 bg-ds-amber-500/10 text-ds-amber-500'
        : tone === 'indigo' ? 'border-ds-indigo-500/40 bg-ds-indigo-500/10 text-ds-indigo-400'
        : 'border-ds-zinc-500/40 bg-ds-zinc-500/10 text-ds-zinc-500',
    )}>
      {children}
    </span>
  );
}

/** Lesbarer Satz zu einem Bedingungs-/Schleifenpfad-Eintrag (COBOL und Java gleich). */
export function guardLabel(entry: PathEntry, t: Translate): string {
  const text = entry.text || entry.condition || '…';
  if (entry.type === 'IF') {
    return entry.branch === 'ELSE'
      ? t('processFlow.guard.ifElse', { text: entry.condition || '…' })
      : t('processFlow.guard.ifThen', { text: entry.condition || '…' });
  }
  if (entry.type === 'EVALUATE' || entry.type === 'SWITCH') {
    const when = entry.when || '…';
    const isOther = when.toUpperCase() === 'OTHER' || when.toLowerCase() === 'default';
    // EVALUATE TRUE ist nur eine Liste von Bedingungen: Das WHEN ist die Bedingung selbst.
    const subject = (entry.subject || '').toUpperCase();
    if (subject === 'TRUE' || subject === 'FALSE') {
      if (isOther) return t('processFlow.guard.otherwise');
      return t(subject === 'TRUE' ? 'processFlow.guard.ifThen' : 'processFlow.guard.ifNot', { text: when });
    }
    return isOther
      ? t('processFlow.guard.other', { subject: entry.subject || '…' })
      : t('processFlow.guard.when', { subject: entry.subject || '…', when });
  }
  if (entry.type === 'LOOP') {
    switch (entry.kind) {
      case 'UNTIL': return t('processFlow.guard.loopUntil', { text });
      case 'VARYING': return t('processFlow.guard.loopVarying', { text });
      case 'TIMES': return t('processFlow.guard.loopTimes', { text });
      case 'FOREVER': return t('processFlow.guard.loopForever');
      case 'WHILE': return t('processFlow.guard.loopWhile', { text });
      case 'DO_WHILE': return t('processFlow.guard.loopDoWhile', { text });
      case 'FOR': return t('processFlow.guard.loopFor', { text });
      case 'FOR_EACH': return t('processFlow.guard.loopForEach', { text });
      default: return text;
    }
  }
  return text;
}

function GuardPill({ entry, isDark, indent, t }: { entry: PathEntry & { dataCount?: number }; isDark: boolean; indent: number; t: Translate }) {
  const isLoop = entry.type === 'LOOP';
  const label = guardLabel(entry, t);
  return (
    <div className="flex min-w-0 items-center gap-1.5" style={{ paddingLeft: `${Math.max(0, indent - 1) * 1.1 + 1.25}rem` }}>
      {isLoop ? <Repeat className="h-3 w-3 shrink-0 text-ds-indigo-400" /> : <Split className="h-3 w-3 shrink-0 text-ds-amber-500" />}
      <span
        title={label}
        className={cn('truncate font-mono text-[0.625rem] italic', isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600')}
      >
        {label}
      </span>
      {entry.dataCount && <span className="shrink-0 text-[0.625rem] text-ds-zinc-500">· {t('processFlow.guardData', { count: entry.dataCount })}</span>}
    </div>
  );
}
