"use client";
import type { CodeEntity } from '@/types/domain';

import { api, API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { buildFlowRows, type DataVerb, type FlowProjection, type FlowRow, type PathEntry } from '@/lib/processFlow';
import { cn } from '@/lib/utils';
import { AlertTriangle, ChevronRight, Database, FileCode, GitBranch, Loader2, RefreshCw, Repeat, Split, Workflow } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

interface Props {
  theme: string;
  focusedEntity: Pick<CodeEntity, 'id' | 'name'> | null;
  projectId?: number | null;
  onFileSelect: (path: string, line?: number | null, sourceId?: number | string | null) => void;
}

type Gate = { truncated: boolean };
const VERB_ORDER: DataVerb[] = ['read', 'write', 'use'];

async function fetchProjection(entityId: number, projectId: number | null | undefined): Promise<{ projection: FlowProjection; truncated: boolean }> {
  const projectParam = projectId ? `&project_id=${projectId}` : '';
  const response = await api.fetch(`${API_URL}/process/focus?entity_id=${entityId}&hops=1&direction=outgoing&node_limit=500&edge_limit=1000${projectParam}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data: FlowProjection & { truncation?: { truncated: boolean } } = await response.json();
  return { projection: { nodes: data.nodes || [], transitions: data.transitions || [] }, truncated: Boolean(data.truncation?.truncated) };
}

export function ProcessFlow({ theme, focusedEntity, projectId, onFileSelect }: Props) {
  const { t } = useLanguage();
  const isDark = theme === 'dark';
  const rootEntityId = focusedEntity?.id ?? null;
  const rootId = rootEntityId != null ? `entity:${rootEntityId}` : null;

  const [projections, setProjections] = useState<Map<string, FlowProjection>>(new Map());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [openData, setOpenData] = useState<Set<string>>(new Set());
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<Gate>({ truncated: false });
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
      setLoadingIds(new Set());
      setGate({ truncated: false });
      setError(null);
      if (rootEntityId != null) load(`entity:${rootEntityId}`, rootEntityId);
    });
    // load hängt nur an projectId/t; ein Sprachwechsel soll nicht neu laden.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootEntityId, projectId]);

  const { rows, capped } = useMemo(
    () => (rootId ? buildFlowRows(rootId, projections, expanded) : { rows: [], capped: false }),
    [rootId, projections, expanded],
  );

  const toggleStep = (row: FlowRow) => {
    if (!row.expandable) return;
    setExpanded(previous => {
      const next = new Set(previous);
      if (next.has(row.key)) next.delete(row.key); else next.add(row.key);
      return next;
    });
    if (!row.expanded && row.nodeId && row.entityId != null) load(row.nodeId, row.entityId);
  };

  const toggleData = (key: string) => setOpenData(previous => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

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
          <div className="text-[0.5625rem] uppercase tracking-wider text-ds-zinc-500">{t('processFlow.subtitle')}</div>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(new Set())}
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

      {(gate.truncated || capped || error) && (
        <div className="px-3 py-1.5 flex flex-wrap gap-2 text-[0.625rem]">
          {error && <span className="rounded border border-ds-red-500/30 bg-ds-red-500/10 px-2 py-1 text-ds-red-400">{error}</span>}
          {(gate.truncated || capped) && (
            <span className="flex items-center gap-1 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 px-2 py-1 text-ds-amber-400">
              <AlertTriangle className="w-3 h-3" />{capped ? t('processFlow.capped') : t('processFlow.truncated')}
            </span>
          )}
        </div>
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
          return (
            <div key={row.key} role="row" className="group/step flex gap-2">
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
                <span className={cn('absolute left-1/2 w-0.5 -translate-x-1/2', isDark ? 'bg-ds-zinc-700' : 'bg-ds-zinc-300', isFirst ? 'top-3.5' : 'top-0', isLast ? 'h-3.5' : 'bottom-0')} />
                <TimelineMarker row={row} isGuard={isGuard} isLoop={isLoopGuard} isDark={isDark} />
              </div>

              <div className={cn('min-w-0 flex-1 pb-2.5', row.lane === 'data' && 'pt-0.5')}>
                {row.lane === 'control' && row.guard && <GuardPill entry={row.guard} isDark={isDark} indent={row.indent} t={t} />}
                {row.lane === 'control' && !row.guard && <StepPill row={row} isDark={isDark} onToggle={toggleStep} onOpen={open} loading={row.nodeId ? loadingIds.has(row.nodeId) : false} t={t} />}
                {row.lane === 'data' && (
                  <div style={{ paddingLeft: `${indentRem + 1.25}rem` }}>
                    <DataCard row={row} isDark={isDark} isOpen={openData.has(row.key)} onToggle={() => toggleData(row.key)} onOpen={open} t={t} />
                  </div>
                )}
                {row.lane === 'external' && <StepPill row={row} isDark={isDark} onToggle={toggleStep} onOpen={open} loading={false} t={t} />}
              </div>
            </div>
          );
        })}
      </div>
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

function StepPill({ row, isDark, onToggle, onOpen, loading, t }: {
  row: FlowRow; isDark: boolean; loading: boolean; t: Translate;
  onToggle: (row: FlowRow) => void;
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
        <button
          type="button"
          onClick={() => onOpen(row)}
          title={row.label}
          className={cn(
            'max-w-full truncate rounded-md border px-2.5 py-1 text-left text-xs font-semibold shadow-sm transition-colors',
            dashed && 'border-dashed',
            isRoot
              ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400'
              : external
                ? (isDark ? 'border-ds-amber-500/60 text-ds-amber-400 hover:bg-ds-amber-500/10' : 'border-ds-amber-500/70 text-ds-amber-700 hover:bg-ds-amber-500/10')
                : (isDark ? 'border-ds-zinc-700 text-ds-zinc-100 hover:border-ds-indigo-500' : 'border-ds-zinc-300 text-ds-zinc-900 hover:border-ds-indigo-500'),
          )}
        >
          {row.label}
        </button>
        <div className="mt-0.5 flex flex-wrap items-center gap-1 empty:hidden">
          {row.cycle && (
            <Badge tone="amber"><Repeat className="h-2.5 w-2.5" />{t(row.cycle === 'recursion' ? 'processFlow.recursion' : 'processFlow.cycle')}</Badge>
          )}
          {row.loop && (
            <Badge tone="indigo"><Repeat className="h-2.5 w-2.5" />{guardLabel({ type: 'LOOP', kind: row.loop.kind, text: row.loop.text }, t)}</Badge>
          )}
          {row.transitionKind === 'jump' && <Badge tone="slate">GOTO</Badge>}
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
    <div className={cn('rounded-md border px-2 py-1 text-[0.625rem]', isDark ? 'border-ds-cyan-500/30 bg-ds-cyan-500/5' : 'border-ds-cyan-500/40 bg-ds-cyan-500/5')}>
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
    return when.toUpperCase() === 'OTHER' || when.toLowerCase() === 'default'
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

function GuardPill({ entry, isDark, indent, t }: { entry: PathEntry; isDark: boolean; indent: number; t: Translate }) {
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
    </div>
  );
}
