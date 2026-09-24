"use client";

import { API_URL, api } from '@/app/services/api';
import type { WorkspaceDocument } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { ProvenanceDisclosure } from '@/components/ProvenanceDisclosure';
import { AlertTriangle, BookOpen, ExternalLink, FileCode2, Loader2, Search, X } from 'lucide-react';
import React from 'react';

type ChangeTarget = {
  label: string;
  entityId?: number;
  filePath?: string | null;
  sourceId?: number | string | null;
};

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
}

function list(value: unknown): RecordValue[] {
  return Array.isArray(value) ? value.filter(item => item && typeof item === 'object' && !Array.isArray(item)) as RecordValue[] : [];
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function number(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function lineLabel(start: unknown, end?: unknown): string {
  const first = number(start);
  if (first === null) return '';
  const last = number(end);
  return `:${first}${last !== null && last !== first ? `-${last}` : ''}`;
}

function isDataRelationship(value: unknown): boolean {
  return /(?:DATA|FILE|READ|WRITE|SQL|TABLE|COLUMN|DATABASE|DB_)/i.test(String(value ?? ''));
}

function isProcessRelationship(value: unknown): boolean {
  return /(?:CALL|PERFORM|INSTANTIAT|GOTO|EXECUTE|INVOKE|PROCESS|BRANCH)/i.test(String(value ?? ''));
}

interface Props {
  projectId?: number | null;
  target: ChangeTarget | null;
  theme: string;
  onOpenCode?: (filePath: string, line: number | null, sourceId: number | string | null) => void;
  onOpenDoc?: (filePath: string, sourceId: number | string | null, locator?: Partial<WorkspaceDocument>) => void;
}

export function ChangePackageAction({ projectId, target, theme, onOpenCode, onOpenDoc }: Props) {
  const { t } = useLanguage();
  const [open, setOpen] = React.useState(false);
  const [description, setDescription] = React.useState('');
  const [direction, setDirection] = React.useState<'incoming' | 'outgoing' | 'both'>('both');
  const [inputMode, setInputMode] = React.useState<'target' | 'diff'>('target');
  const [baseRef, setBaseRef] = React.useState('');
  const [headRef, setHeadRef] = React.useState('');
  const [diffSourceId, setDiffSourceId] = React.useState('');
  const [packageData, setPackageData] = React.useState<RecordValue | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const isDark = theme === 'dark';

  const runAnalysis = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!projectId || !target || !description.trim() || (inputMode === 'diff' && (!baseRef.trim() || !headRef.trim()))) return;
    setLoading(true);
    setError(null);
    setPackageData(null);
    try {
      const params = new URLSearchParams({ direction, hops: '2', limit: '40' });
      if (inputMode === 'diff') {
        params.set('base_ref', baseRef.trim());
        params.set('head_ref', headRef.trim());
        const sourceId = diffSourceId.trim() || String(target.sourceId ?? '');
        if (sourceId) params.set('source_id', sourceId);
      } else {
        if (target.entityId) params.set('entity_id', String(target.entityId));
        if (target.filePath) params.set('file_path', target.filePath);
      }
      const response = await api.fetch(`${API_URL}/projects/${projectId}/change-package?${params}`);
      const data: unknown = await response.json();
      if (!response.ok) {
        throw new Error(text(record(data).detail, `HTTP ${response.status}`));
      }
      setPackageData(record(data));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('changePackage.loadError'));
    } finally {
      setLoading(false);
    }
  };

  const openCode = (filePath: unknown, line: unknown, sourceId: unknown) => {
    if (typeof filePath !== 'string' || !filePath || !onOpenCode) return;
    setOpen(false);
    onOpenCode(filePath, number(line), typeof sourceId === 'string' || typeof sourceId === 'number' ? sourceId : null);
  };

  const openDocument = (item: RecordValue) => {
    const evidence = record(item.evidence);
    const filePath = text(evidence.file_path);
    const sourceId = evidence.source_id;
    if (filePath && (typeof sourceId === 'number' || typeof sourceId === 'string') && onOpenDoc) {
      setOpen(false);
      onOpenDoc(filePath, sourceId, {
        url: text(item.url) || null,
        excerpt: text(evidence.excerpt) || undefined,
        chunkId: number(evidence.chunk_id) ?? undefined,
        startLine: number(evidence.start_line),
        endLine: number(evidence.end_line),
        page: number(evidence.page),
        section: text(evidence.section) || undefined,
        urlAnchor: text(evidence.url_anchor) || undefined,
        type: text(item.source_type) || undefined,
      });
      return;
    }
    const url = text(item.url);
    if (url && typeof window !== 'undefined') window.open(url, '_blank', 'noopener,noreferrer');
  };

  const impact = record(packageData?.change_impact);
  const impactTarget = record(impact.target);
  const scope = record(packageData?.scope);
  const nodes = list(impact.nodes);
  const sourceForEntity = (id: unknown) => nodes.find(node => node.id === id)?.source_id ?? target?.sourceId ?? null;
  const codeItems = list(packageData?.affected_code);
  const codeEdges = list(impact.edges);
  const targetEntityIds = new Set(
    Array.isArray(record(impact.target).entity_ids)
      ? (record(impact.target).entity_ids as unknown[]).filter((id): id is number => typeof id === 'number')
      : [],
  );
  const directEdges = codeEdges.filter(edge => targetEntityIds.has(number(edge.source) ?? -1) || targetEntityIds.has(number(edge.target) ?? -1));
  const dataEdges = directEdges.filter(edge => isDataRelationship(edge.type));
  const processEdges = directEdges.filter(edge => !isDataRelationship(edge.type) && isProcessRelationship(edge.type));
  const dependencyEdges = directEdges.filter(edge => !isDataRelationship(edge.type) && !isProcessRelationship(edge.type));
  const linkedKnowledge = list(packageData?.linked_knowledge);
  const possibleRules = linkedKnowledge.filter(item => item.classification === 'possible_domain_rule');
  const documents = linkedKnowledge.filter(item => item.classification !== 'possible_domain_rule');
  const issues = list(packageData?.historical_issues);
  const tests = record(packageData?.tests);
  const testItems = list(tests.items);
  const responsibility = record(packageData?.responsibility);
  const responsibilityItems = list(responsibility.items);
  const unknownEdges = list(impact.unknown_edges);
  const evidenceGaps = Array.isArray(packageData?.evidence_gaps)
    ? packageData.evidence_gaps.filter((item): item is string => typeof item === 'string')
    : [];
  const limitations = Array.isArray(packageData?.limitations)
    ? packageData.limitations.filter((item): item is string => typeof item === 'string')
    : [];
  const presentation = record(packageData?.presentation_truncated);
  const truncated = Boolean(record(packageData?.scope).truncated || tests.truncated || responsibility.partial ||
    presentation.affected_code || presentation.linked_knowledge || presentation.historical_issues ||
    presentation.documents || evidenceGaps.some(gap => /truncat|gekürzt/i.test(gap)));
  const analyzedDirection = scope.direction === 'outgoing'
    ? t('changePackage.directionOutgoing')
    : scope.direction === 'both'
      ? t('changePackage.directionBoth')
      : t('changePackage.directionIncoming');

  const muted = isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600';
  const border = isDark ? 'border-ds-zinc-700' : 'border-ds-zinc-200';
  const sectionClass = `rounded-lg border ${border} p-3`;
  const OpenCode = ({ path, line, sourceId, label }: { path: unknown; line?: unknown; sourceId?: unknown; label?: string }) => {
    const filePath = text(path);
    if (!filePath || !onOpenCode) return null;
    return (
      <button type="button" onClick={() => openCode(filePath, line, sourceId)} className="inline-flex items-center gap-1 text-[11px] text-ds-indigo-400 hover:text-ds-indigo-300 underline underline-offset-2">
        <FileCode2 className="h-3 w-3 shrink-0" />{label || `${filePath}${lineLabel(line)}`}
      </button>
    );
  };
  const OpenDoc = ({ item }: { item: RecordValue }) => {
    const evidence = record(item.evidence);
    const hasInternalTarget = Boolean(text(evidence.file_path) && evidence.source_id != null && onOpenDoc);
    const url = text(item.url);
    if (!hasInternalTarget && !url) return null;
    return hasInternalTarget ? (
      <button type="button" onClick={() => openDocument(item)} className="inline-flex items-center gap-1 text-[11px] text-ds-emerald-400 hover:text-ds-emerald-300 underline underline-offset-2">
        <BookOpen className="h-3 w-3 shrink-0" />{t('changePackage.openEvidence')}
      </button>
    ) : (
      <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-ds-emerald-400 hover:text-ds-emerald-300 underline underline-offset-2">
        <ExternalLink className="h-3 w-3 shrink-0" />{t('changePackage.openEvidence')}
      </a>
    );
  };
  const relationshipRows = (edges: RecordValue[]) => edges.slice(0, 40).map((edge, index) => {
    const sourceNode = nodes.find(node => node.id === edge.source);
    const targetNode = nodes.find(node => node.id === edge.target);
    const edgePath = text(sourceNode?.file_path);
    const sourceProvenance = record(sourceNode?.provenance);
    const relationshipProvenance = Object.keys(sourceProvenance).length
      ? {
          ...sourceProvenance,
          certainty: text(edge.certainty, text(edge.resolution)),
          origin: text(edge.type),
          locator: { file_path: edgePath, start_line: edge.start_line, end_line: edge.end_line },
        }
      : null;
    return <div key={`${String(edge.id)}-${index}`} className={`flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-[11px] ${border}`}>
      <span>{text(sourceNode?.qualified_name, text(sourceNode?.name, String(edge.source)))} — <strong>{text(edge.type)}</strong> ({text(edge.resolution)}) → {text(targetNode?.qualified_name, text(targetNode?.name, text(edge.target_name)))}</span>
      <ProvenanceDisclosure provenance={relationshipProvenance} theme={theme} />
      <OpenCode path={edgePath} line={edge.start_line} sourceId={sourceNode?.source_id} label={t('changePackage.openRelationshipEvidence', { location: `${edgePath}${lineLabel(edge.start_line, edge.end_line)}` })} />
    </div>;
  });

  if (!projectId || !target || (!target.entityId && !target.filePath)) return null;

  return (
    <>
      <button
        type="button"
        data-testid="investigate-change"
        onClick={() => setOpen(true)}
        title={t('changePackage.actionTitle')}
        className="inline-flex h-7 items-center gap-1.5 rounded border border-ds-indigo-500/50 bg-ds-indigo-500/10 px-2.5 text-[10px] font-semibold text-ds-indigo-400 hover:bg-ds-indigo-500/20"
      >
        <Search className="h-3.5 w-3.5" />{t('changePackage.action')}
      </button>

      {open && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-ds-black/60 p-3 sm:p-6" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false); }}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="change-package-title"
            className={`flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border shadow-2xl ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-950 text-ds-zinc-100' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-900'}`}
          >
            <header className={`flex items-start gap-4 border-b p-4 ${border}`}>
              <div className="min-w-0 flex-1">
                <h2 id="change-package-title" className="text-sm font-semibold">{t('changePackage.title')}</h2>
                <p className={`mt-1 truncate text-xs ${muted}`} title={target.label}>{target.label}</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label={t('changePackage.close')} className={`rounded p-1 ${muted}`}><X className="h-4 w-4" /></button>
            </header>

            <form onSubmit={runAnalysis} className={`border-b p-4 ${border}`}>
              <label htmlFor="change-package-description" className="mb-1.5 block text-xs font-semibold">{t('changePackage.descriptionLabel')}</label>
              <textarea
                id="change-package-description"
                value={description}
                onChange={event => setDescription(event.target.value)}
                maxLength={1200}
                rows={3}
                placeholder={t('changePackage.descriptionPlaceholder')}
                className={`w-full resize-y rounded-md border px-3 py-2 text-xs outline-none focus:border-ds-indigo-500 ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100 placeholder:text-ds-zinc-500' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-900 placeholder:text-ds-zinc-400'}`}
              />
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
                <label className="flex items-center gap-1.5"><input type="radio" name="change-package-mode" checked={inputMode === 'target'} onChange={() => setInputMode('target')} />{t('changePackage.targetMode')}</label>
                <label className="flex items-center gap-1.5"><input type="radio" name="change-package-mode" checked={inputMode === 'diff'} onChange={() => setInputMode('diff')} />{t('changePackage.diffMode')}</label>
              </div>
              {inputMode === 'diff' && <div className="mt-2 flex flex-wrap gap-2">
                <label className={`flex flex-col gap-1 text-[10px] ${muted}`} htmlFor="change-package-base">{t('changePackage.baseRevision')}
                  <input id="change-package-base" value={baseRef} onChange={event => setBaseRef(event.target.value)} maxLength={256} required className={`h-8 rounded-md border px-2 text-xs ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-white text-ds-zinc-900'}`} />
                </label>
                <label className={`flex flex-col gap-1 text-[10px] ${muted}`} htmlFor="change-package-head">{t('changePackage.headRevision')}
                  <input id="change-package-head" value={headRef} onChange={event => setHeadRef(event.target.value)} maxLength={256} required className={`h-8 rounded-md border px-2 text-xs ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-white text-ds-zinc-900'}`} />
                </label>
                <label className={`flex flex-col gap-1 text-[10px] ${muted}`} htmlFor="change-package-source">{t('changePackage.sourceId')}
                  <input id="change-package-source" type="number" min="1" step="1" value={diffSourceId || String(target.sourceId ?? '')} onChange={event => setDiffSourceId(event.target.value)} className={`h-8 w-24 rounded-md border px-2 text-xs ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-300 bg-white text-ds-zinc-900'}`} />
                </label>
                <p className={`self-end pb-1 text-[10px] ${muted}`}>{t('changePackage.diffHint')}</p>
              </div>}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <p className={`max-w-2xl text-[10px] ${muted}`}>{t('changePackage.descriptionHint')}</p>
                <div className="flex flex-wrap items-end gap-2">
                  <label className={`flex flex-col gap-1 text-[10px] ${muted}`} htmlFor="change-package-direction">
                    {t('changePackage.directionLabel')}
                    <select
                      id="change-package-direction"
                      value={direction}
                      onChange={event => setDirection(event.target.value as 'incoming' | 'outgoing' | 'both')}
                      className={`h-8 rounded-md border px-2 text-xs ${isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-200' : 'border-ds-zinc-300 bg-white text-ds-zinc-800'}`}
                    >
                      <option value="incoming">{t('changePackage.directionIncoming')}</option>
                      <option value="outgoing">{t('changePackage.directionOutgoing')}</option>
                      <option value="both">{t('changePackage.directionBoth')}</option>
                    </select>
                  </label>
                  <button type="submit" disabled={loading || !description.trim() || (inputMode === 'diff' && (!baseRef.trim() || !headRef.trim()))} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-ds-indigo-600 px-3 text-xs font-semibold text-white hover:bg-ds-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">
                    {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                    {loading ? t('changePackage.loading') : t('changePackage.run')}
                  </button>
                </div>
              </div>
            </form>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {error && <p role="alert" className="rounded border border-ds-red-500/30 bg-ds-red-500/10 p-3 text-xs text-ds-red-400">{error}</p>}
              {!packageData && !error && <p className={`py-6 text-center text-xs ${muted}`}>{t('changePackage.intro')}</p>}
              {packageData && (
                <>
                  {truncated && <p className="flex items-center gap-2 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 p-2.5 text-xs text-ds-amber-400"><AlertTriangle className="h-4 w-4 shrink-0" />{t('changePackage.truncated')}</p>}
                  <p className={`text-[10px] ${muted}`}>{t('changePackage.scopeSummary', {
                    direction: analyzedDirection,
                    hops: number(scope.hops) ?? 2,
                    nodes: nodes.length,
                    edges: codeEdges.length,
                  })}</p>
                  {impactTarget.kind === 'diff' && <section className={sectionClass}>
                    <h3 className="mb-1 text-xs font-semibold">{t('changePackage.diffSummary')}</h3>
                    <p className={`break-all text-[10px] ${muted}`}>{text(impactTarget.base_commit)} → {text(impactTarget.head_commit)}</p>
                    <p className={`mt-1 text-[10px] ${muted}`}>{t('changePackage.diffFiles', { count: Array.isArray(impactTarget.changed_files) ? impactTarget.changed_files.length : 0 })}</p>
                    <p className="mt-1 break-words text-xs">{Array.isArray(impactTarget.changed_files) ? impactTarget.changed_files.join(', ') : ''}</p>
                    {Array.isArray(impactTarget.unindexed_files) && impactTarget.unindexed_files.length > 0 && <p className={`mt-1 text-[10px] ${muted}`}>{t('changePackage.unindexedFiles')}: {impactTarget.unindexed_files.join(', ')}</p>}
                  </section>}
                  <section className="rounded-lg border border-ds-indigo-500/30 bg-ds-indigo-500/5 p-3">
                    <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-ds-indigo-400">{t('changePackage.requestedChange')}</h3>
                    <p className="whitespace-pre-wrap text-xs">{description.trim()}</p>
                  </section>
                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.affectedCode')} · {codeItems.length}</h3>
                    {codeItems.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noIndexedImpact')}</p>}
                    <div className="space-y-2">
                      {codeItems.map((item, index) => {
                        const path = text(item.file_path);
                        const itemId = item.id;
                        const relationPath = record(item.relationship_path);
                        const isChangeTarget = number(relationPath.hops) === 0;
                        const pathEdges = list(relationPath.edges);
                        return (
                          <article key={`${String(itemId)}-${index}`} className={`rounded-md border p-2.5 ${border}`}>
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="min-w-0">
                                <p className="truncate text-xs font-medium">{text(item.qualified_name, text(item.name, t('changePackage.unknownName')))}{isChangeTarget && <span className="ml-2 rounded bg-ds-indigo-500/15 px-1.5 py-0.5 text-[9px] font-semibold text-ds-indigo-400">{t('changePackage.changeTarget')}</span>}</p>
                                <p className={`truncate text-[10px] ${muted}`}>{path}{lineLabel(item.start_line, item.end_line)}</p>
                                <ProvenanceDisclosure provenance={item.provenance ?? record(item.evidence).provenance} theme={theme} />
                              </div>
                              <OpenCode path={path} line={item.start_line} sourceId={item.source_id} />
                            </div>
                            {pathEdges.length > 0 && (
                              <ol className={`mt-2 space-y-1 border-l pl-3 text-[10px] ${border} ${muted}`}>
                                {pathEdges.map((edge, edgeIndex) => {
                                  const edgePath = text(edge.evidence_file);
                                  const sourceEntity = nodes.find(node => node.file_path === edgePath);
                                  return (
                                    <li key={`${String(edge.edge_id)}-${edgeIndex}`} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                      <span>{text(edge.relationship)} · {text(edge.resolution)} · {edge.traversed_against_relationship ? t('changePackage.reverseTraversal') : t('changePackage.forwardTraversal')} · {t('changePackage.hopCount', { count: number(edge.hops) ?? edgeIndex + 1 })}</span>
                                      <OpenCode path={edgePath} line={edge.evidence_start_line} sourceId={sourceEntity?.source_id ?? item.source_id} label={t('changePackage.openRelationshipEvidence', { location: `${edgePath}${lineLabel(edge.evidence_start_line, edge.evidence_end_line)}` })} />
                                    </li>
                                  );
                                })}
                              </ol>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-1 text-xs font-semibold">{t('changePackage.affectedProcesses')} · {processEdges.length}</h3>
                    <p className={`mb-2 text-[10px] ${muted}`}>{t('changePackage.processEdgeHint')}</p>
                    {processEdges.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noRelationships')}</p>}
                    <div className="space-y-1.5">{relationshipRows(processEdges)}</div>
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.directCodeDependencies')} · {dependencyEdges.length}</h3>
                    {dependencyEdges.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noRelationships')}</p>}
                    <div className="space-y-1.5">{relationshipRows(dependencyEdges)}</div>
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.dataAccesses')} · {dataEdges.length}</h3>
                    {dataEdges.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noRelationships')}</p>}
                    <div className="space-y-1.5">{relationshipRows(dataEdges)}</div>
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-1 text-xs font-semibold">{t('changePackage.domainRules')} · {possibleRules.length}</h3>
                    <p className={`mb-2 text-[10px] ${muted}`}>{t('changePackage.rulesUnverified')}</p>
                    {possibleRules.map((item, index) => <article key={`${String(item.entity_id)}-${index}`} className={`mb-2 rounded border p-2.5 last:mb-0 ${border}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-medium">{text(item.title)}</p><OpenDoc item={item} /></div>
                      <p className={`mt-1 text-[10px] ${muted}`}>{text(record(item.evidence).excerpt, text(record(item.evidence).context))}</p>
                      <p className="mt-1 text-[10px] text-ds-amber-400">{text(item.classification_basis)} · {text(item.classification_keyword)}</p>
                      <ProvenanceDisclosure provenance={record(item.evidence).provenance} theme={theme} />
                    </article>)}
                    {possibleRules.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noRules')}</p>}
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.documents')} · {documents.length}</h3>
                    {documents.map((item, index) => <article key={`${String(item.entity_id)}-${index}`} className={`mb-2 rounded border p-2.5 last:mb-0 ${border}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-medium">{text(item.title)}</p><OpenDoc item={item} /></div>
                      <p className={`mt-1 text-[10px] ${muted}`}>{text(record(item.evidence).context, text(record(item.evidence).excerpt))}</p>
                      <p className={`mt-1 text-[10px] ${muted}`}>{text(item.source_type)} · {text(record(item.evidence).status)} · {t('changePackage.linkedRecordOnly')}</p>
                      <ProvenanceDisclosure provenance={record(item.evidence).provenance} theme={theme} />
                    </article>)}
                    {documents.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noDocuments')}</p>}
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.history')} · {issues.length}</h3>
                    {issues.map((item, index) => <article key={`${String(item.issue_key)}-${index}`} className={`mb-2 rounded border p-2.5 last:mb-0 ${border}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-medium">{text(item.issue_key, text(item.title))}</p><OpenDoc item={item} /></div>
                      <p className={`mt-1 text-[10px] ${muted}`}>{item.bug_candidate ? t('changePackage.bugCandidate') : t('changePackage.issueTypeUnknown')} · {text(item.classification_basis)}</p>
                    </article>)}
                    {issues.length === 0 && <p className={`text-xs ${muted}`}>{t('changePackage.noHistory')}</p>}
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.tests')} · {testItems.length}</h3>
                    {testItems.map((item, index) => {
                      const entity = record(item.entity);
                      const evidence = record(item.evidence);
                      return <div key={`${String(entity.id)}-${index}`} className={`mb-2 flex flex-wrap items-center justify-between gap-2 rounded border p-2 last:mb-0 ${border}`}>
                        <span className="text-xs">{text(entity.name)} · {text(item.relationship)}</span>
                        <div className="flex flex-wrap items-center gap-1"><ProvenanceDisclosure provenance={item.provenance} theme={theme} /><OpenCode path={entity.file_path} line={evidence.start_line ?? entity.start_line} sourceId={entity.source_id} /></div>
                      </div>;
                    })}
                    {testItems.length === 0 && <p className={`text-xs ${muted}`}>{text(tests.note, t('changePackage.testsUnknown'))}</p>}
                    <p className={`mt-2 text-[10px] ${muted}`}>{t('changePackage.noCoverageClaim')}</p>
                  </section>

                  <section className={sectionClass}>
                    <h3 className="mb-2 text-xs font-semibold">{t('changePackage.unknownAreas')}</h3>
                    {unknownEdges.length > 0 && <div className="mb-2 space-y-1.5">
                      {unknownEdges.slice(0, 30).map((edge, index) => <div key={`${String(edge.id)}-${index}`} className={`flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-[11px] ${border}`}>
                        <span>{text(edge.source_name)} — {text(edge.type)} → {text(edge.target_name)} ({text(edge.resolution)})</span>
                        <OpenCode path={edge.file_path} line={edge.start_line} sourceId={sourceForEntity(edge.source_entity_id)} />
                      </div>)}
                    </div>}
                    {evidenceGaps.map((gap, index) => <p key={`gap-${index}`} className={`mb-1 text-[11px] ${muted}`}>• {gap}</p>)}
                    {limitations.map((limitation, index) => <p key={`limitation-${index}`} className={`mb-1 text-[11px] ${muted}`}>• {limitation}</p>)}
                    {responsibilityItems.length > 0 && <div className="mt-2">
                      <p className="mb-1 text-[10px] font-semibold">{t('changePackage.responsibility')}</p>
                      {responsibilityItems.map((item, index) => <p key={`owner-${index}`} className={`text-[10px] ${muted}`}>
                        <span>{Array.isArray(item.owners) ? item.owners.join(', ') : t('changePackage.unknownOwner')} · {Array.isArray(item.files) ? item.files.join(', ') : ''} · CODEOWNERS</span>
                        <span className="ml-2"><OpenCode path={record(item.source).file_path} sourceId={item.source_id} /></span>
                      </p>)}
                    </div>}
                    {list(responsibility.unknown_files).length > 0 && <p className={`mt-1 text-[10px] ${muted}`}>{t('changePackage.unknownOwnerFiles', { count: list(responsibility.unknown_files).length })}</p>}
                  </section>
                </>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
