"use client";

import { API_URL } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { getEntityTypeLabel } from '@/lib/graphTaxonomy';
import { cn } from '@/lib/utils';
import { WEB_LINK_MESSAGE, addWebAnchorScroll, buildWebDocumentHtml, webAssetHref, type WebCrumb, type WebDocumentData, type WebFact, type WebRelated } from '@/lib/webDocumentHtml';
import { useGraphStyleRevision } from '@/hooks/useGraphStyleRevision';
import { AlertTriangle, ChevronRight, Code2, ExternalLink, Paperclip, Link2 } from 'lucide-react';
import React, { useEffect, useMemo, useRef } from 'react';

const TRANSLATED_FACTS = new Set([
  'type', 'status', 'priority', 'resolution', 'assignee', 'reporter', 'labels', 'components', 'fix_versions', 'affects_versions',
  'due', 'created', 'updated', 'space', 'version', 'modified_by', 'author', 'milestone', 'closed',
]);
const TRANSLATED_RELATIONS = new Set(['parent', 'subtask']);

interface Props {
  document: WebDocumentData;
  theme: string;
  anchor?: string | null;
  /** Öffnet einen Eintrag, den der Index kennt, in Doctus statt im fremden System. */
  onOpenKnown: (url: string, sourceId: number) => void;
  onOpenCode: (path: string, line: number | null | undefined, sourceId: number | null | undefined) => void;
}

function formatSize(bytes: number | null | undefined): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function WebDocumentView({ document: doc, theme, anchor, onOpenKnown, onOpenCode }: Props) {
  const { t, language } = useLanguage();
  const isDark = theme === 'dark';
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const styleRevision = useGraphStyleRevision();

  const formatDate = useMemo(() => (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString(language === 'de' ? 'de-DE' : 'en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
  }, [language]);

  const srcDoc = useMemo(() => {
    // Die Farben werden neu aufgelöst, sobald das Theme der App wechselt.
    void styleRevision;
    return addWebAnchorScroll(buildWebDocumentHtml(doc, theme, API_URL, {
      empty: t('webDocument.emptyBody'),
      comments: (shown, total) => (shown < total ? t('webDocument.commentsPartial', { shown, total }) : t('webDocument.comments', { count: total })),
      formatDate,
    }), anchor);
  }, [doc, theme, anchor, styleRevision, t, formatDate]);

  useEffect(() => {
    const handle = (event: MessageEvent) => {
      // Nur das eigene iframe zählt; es liefert höchstens eine Adresse und eine Quellen-Nummer.
      if (event.source !== frameRef.current?.contentWindow || event.data?.type !== WEB_LINK_MESSAGE) return;
      const sourceId = Number(event.data.sourceId);
      if (typeof event.data.url === 'string' && Number.isInteger(sourceId)) onOpenKnown(event.data.url, sourceId);
    };
    window.addEventListener('message', handle);
    return () => window.removeEventListener('message', handle);
  }, [onOpenKnown]);

  const factLabel = (fact: WebFact) => (TRANSLATED_FACTS.has(fact.key) ? t(`webDocument.facts.${fact.key}`) : fact.label);
  const relationLabel = (item: WebRelated) => (TRANSLATED_RELATIONS.has(item.relation) ? t(`webDocument.relations.${item.relation}`) : item.relation);
  const muted = isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600';
  const border = isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200';

  const crumb = (item: WebCrumb, index: number) => {
    const known = item.url && item.source_id != null;
    return (
      <React.Fragment key={`${item.title}-${index}`}>
        {index > 0 && <ChevronRight className="h-3 w-3 shrink-0 opacity-50" aria-hidden />}
        {known ? (
          <button type="button" className="truncate hover:underline" onClick={() => onOpenKnown(item.url!, item.source_id!)}>{item.title}</button>
        ) : item.url ? (
          <a className="truncate hover:underline" href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a>
        ) : <span className="truncate">{item.title}</span>}
      </React.Fragment>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="web-document">
      <header className={cn('shrink-0 space-y-1.5 border-b px-4 py-3', border)}>
        {doc.breadcrumbs.length > 0 && (
          <nav aria-label={t('webDocument.breadcrumbs')} className={cn('flex flex-wrap items-center gap-1 text-[0.6875rem]', muted)}>
            {doc.breadcrumbs.map(crumb)}
          </nav>
        )}
        <h1 className={cn('text-sm font-bold leading-snug', isDark ? 'text-ds-zinc-100' : 'text-ds-zinc-900')}>
          {doc.identifier && <span className="mr-1.5 font-mono text-xs text-ds-indigo-400">{doc.identifier}</span>}
          {doc.title}
        </h1>
        {doc.facts.length > 0 && (
          <dl className="flex flex-wrap gap-x-3 gap-y-1 text-[0.6875rem]">
            {doc.facts.map(fact => (
              <div key={fact.key} className="flex flex-wrap items-center gap-1">
                <dt className={muted}>{factLabel(fact)}:</dt>
                {fact.values.map(value => (
                  <dd key={value} className={cn(
                    'rounded px-1.5 py-0.5 font-medium',
                    fact.kind === 'status' ? 'bg-ds-indigo-500/15 text-ds-indigo-400' : isDark ? 'bg-ds-zinc-800 text-ds-zinc-200' : 'bg-ds-zinc-100 text-ds-zinc-800',
                  )}>{fact.kind === 'date' ? formatDate(value) : value}</dd>
                ))}
              </div>
            ))}
          </dl>
        )}
        {doc.notice && (
          <p role="status" className="flex items-start gap-1.5 rounded border border-ds-amber-500/30 bg-ds-amber-500/10 px-2 py-1 text-[0.6875rem] text-ds-amber-400">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
            <span>
              {t(`webDocument.notice.${doc.notice}`)}
              {doc.synced_at ? ` ${t('webDocument.syncedAt', { date: formatDate(doc.synced_at) })}` : ''}
            </span>
          </p>
        )}
        {(doc.code_refs?.length ?? 0) > 0 && (
          <details open className="text-[0.6875rem]" data-testid="web-code-refs">
            <summary className={cn('flex cursor-pointer items-center gap-1 font-semibold', muted)} title={t('webDocument.codeRefsHint')}>
              <Code2 className="h-3 w-3" aria-hidden />{t('webDocument.codeRefs', { count: doc.code_refs?.length ?? 0 })}
            </summary>
            <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto">
              {doc.code_refs?.map(ref => (
                <li key={ref.entity_id} className="flex flex-wrap items-center gap-1.5">
                  <button type="button" className="text-left font-mono text-ds-indigo-400 hover:underline" title={ref.cite} onClick={() => onOpenCode(ref.file_path, ref.start_line, ref.source_id)}>{ref.name}</button>
                  <span className={muted}>{getEntityTypeLabel(ref.type, language)} · {ref.file_path.split('/').pop()}</span>
                  {ref.mentions > 1 && <span className={muted}>{t('webDocument.mentions', { count: ref.mentions })}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}
        {doc.related.length > 0 && (          <details className="text-[0.6875rem]">
            <summary className={cn('flex cursor-pointer items-center gap-1 font-semibold', muted)}>
              <Link2 className="h-3 w-3" aria-hidden />{t('webDocument.related', { count: doc.related.length })}
            </summary>
            <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto">
              {doc.related.map(item => {
                const label = <>{item.identifier && <span className="mr-1 font-mono">{item.identifier}</span>}{item.title}</>;
                return (
                  <li key={`${item.relation}-${item.url}`} className="flex flex-wrap items-center gap-1.5">
                    <span className={muted}>{relationLabel(item)}</span>
                    {item.source_id != null ? (
                      <button type="button" className="text-left text-ds-indigo-400 hover:underline" onClick={() => onOpenKnown(item.url, item.source_id!)}>{label}</button>
                    ) : (
                      <a className="inline-flex items-center gap-1 text-ds-indigo-400 hover:underline" href={item.url} target="_blank" rel="noopener noreferrer">
                        {label}<ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                      </a>
                    )}
                    {item.status && <span className={muted}>({item.status})</span>}
                  </li>
                );
              })}
            </ul>
          </details>
        )}
        {doc.attachments.length > 0 && (
          <details className="text-[0.6875rem]">
            <summary className={cn('flex cursor-pointer items-center gap-1 font-semibold', muted)}>
              <Paperclip className="h-3 w-3" aria-hidden />{t('webDocument.attachments', { count: doc.attachments.length })}
            </summary>
            <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto">
              {doc.attachments.map(item => (
                <li key={item.url} className="flex flex-wrap items-center gap-1.5">
                  <a className="text-ds-indigo-400 hover:underline" href={webAssetHref(item.url, API_URL)} target="_blank" rel="noopener noreferrer">{item.name}</a>
                  {item.size ? <span className={muted}>{formatSize(item.size)}</span> : null}
                </li>
              ))}
            </ul>
          </details>
        )}
      </header>
      <iframe
        ref={frameRef}
        srcDoc={srcDoc}
        className={cn('min-h-0 w-full flex-1 border-none', isDark ? 'bg-ds-zinc-950' : 'bg-ds-white')}
        title={doc.title}
        sandbox="allow-popups allow-popups-to-escape-sandbox allow-scripts"
      />
    </div>
  );
}
