'use client';

import { useLanguage } from '@/lib/i18n/LanguageContext';
import { ChevronDown, Info } from 'lucide-react';
import React from 'react';

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : {};
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function locatorLabel(value: unknown): string | null {
  const locator = record(value);
  const file = stringValue(locator.file_path) ?? stringValue(locator.file);
  const start = typeof locator.start_line === 'number' ? locator.start_line :
    Array.isArray(locator.lines) && typeof locator.lines[0] === 'number' ? locator.lines[0] : null;
  const end = typeof locator.end_line === 'number' ? locator.end_line :
    Array.isArray(locator.lines) && typeof locator.lines[1] === 'number' ? locator.lines[1] : null;
  const fileLocation = file
    ? `${file}${start != null ? `:${start}${end != null && end !== start ? `-${end}` : ''}` : ''}`
    : null;
  const page = typeof locator.page === 'number' ? `S. ${locator.page}` : null;
  const section = stringValue(locator.section);
  const anchor = stringValue(locator.url_anchor);
  return [fileLocation, page, section, anchor].filter(Boolean).join(' · ') || stringValue(locator.url);
}

function formatDate(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

interface Props {
  provenance?: unknown;
  theme: string;
  className?: string;
}

/** Compact, shared disclosure for source, revision, review state, and locator. */
export function ProvenanceDisclosure({ provenance, theme, className = '' }: Props) {
  const { t, language } = useLanguage();
  const data = record(provenance);
  if (!Object.keys(data).length) return null;

  const isDark = theme === 'dark';
  const kind = stringValue(data.kind) ?? 'unknown';
  const status = stringValue(data.verification_status) ?? 'unavailable';
  const revision = stringValue(data.source_revision);
  const sourceName = stringValue(data.source_name);
  const sourceType = stringValue(data.source_type);
  const branch = stringValue(data.branch);
  const lastSyncedAt = stringValue(data.last_synced_at);
  const syncStatus = stringValue(data.sync_status);
  const associationStatus = stringValue(data.association_status);
  const associationReviewedAt = stringValue(data.association_reviewed_at);
  const certainty = stringValue(data.certainty);
  const origin = stringValue(data.origin);
  const analysisStatus = stringValue(data.analysis_status);
  const analysisReasons = Array.isArray(data.analysis_reasons)
    ? data.analysis_reasons.filter((reason): reason is string => typeof reason === 'string')
    : [];
  const locator = locatorLabel(data.locator);
  const detail = stringValue(data.verification_note);
  const revisionKind = stringValue(data.revision_kind);
  const panel = isDark
    ? 'border-ds-zinc-800 bg-ds-zinc-950/80 text-ds-zinc-300'
    : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-700';
  const subtle = isDark ? 'text-ds-zinc-500' : 'text-ds-zinc-550';
  const summaryText = isDark ? 'text-ds-zinc-400 hover:text-ds-zinc-200' : 'text-ds-zinc-600 hover:text-ds-zinc-900';

  const valueFor = (key: string, raw?: string | null) => {
    if (key === 'kind') return t(`provenance.kind.${kind}`);
    if (key === 'status') return t(`provenance.status.${status}`);
    if (raw == null) return t('provenance.notAvailable');
    return raw;
  };
  const dateValue = (value: string | null) => value ? formatDate(value, language === 'de' ? 'de-DE' : 'en-US') : t('provenance.notAvailable');

  return (
    <details className={`group min-w-0 max-w-full ${className}`}>
      <summary className={`inline-flex max-w-full cursor-pointer list-none items-center gap-1 rounded px-1.5 py-1 text-[10px] ${summaryText} [&::-webkit-details-marker]:hidden`}>
        <Info className="h-3 w-3 shrink-0" />
        <span className="truncate">{valueFor('kind')}</span>
        <span className="truncate">· {valueFor('status')}</span>
        <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className={`mt-1 w-[min(22rem,calc(100vw-2rem))] max-w-full rounded-md border p-2.5 shadow-xl ${panel}`}>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[10px]">
          <dt className={subtle}>{t('provenance.kindLabel')}</dt><dd>{valueFor('kind')}</dd>
          <dt className={subtle}>{t('provenance.statusLabel')}</dt><dd>{valueFor('status')}</dd>
          <dt className={subtle}>{t('provenance.sourceLabel')}</dt><dd>{[sourceName, sourceType].filter(Boolean).join(' · ') || t('provenance.notAvailable')}</dd>
          <dt className={subtle}>{t('provenance.revisionLabel')}</dt>
          <dd className="min-w-0 break-all" title={revision ?? undefined}>
            {revision ? <><code>{revision.slice(0, 12)}{revisionKind === 'content_hash' ? ` · ${t('provenance.contentHash')}` : ''}</code>{branch && <span> · {branch}</span>}</> : t('provenance.notAvailable')}
          </dd>
          <dt className={subtle}>{t('provenance.lastSyncLabel')}</dt><dd>{dateValue(lastSyncedAt)}</dd>
          {syncStatus && <><dt className={subtle}>{t('provenance.syncStatusLabel')}</dt><dd>{syncStatus}</dd></>}
          {associationStatus && <><dt className={subtle}>{t('provenance.associationStatusLabel')}</dt><dd>{associationStatus === 'approved' ? t('provenance.associationApproved') : associationStatus}</dd></>}
          {associationReviewedAt && <><dt className={subtle}>{t('provenance.associationReviewLabel')}</dt><dd>{dateValue(associationReviewedAt)}</dd></>}
          {certainty && <><dt className={subtle}>{t('provenance.certaintyLabel')}</dt><dd>{certainty}</dd></>}
          {origin && <><dt className={subtle}>{t('provenance.originLabel')}</dt><dd>{origin}</dd></>}
          {analysisStatus && <><dt className={subtle}>{t('provenance.analysisStatusLabel')}</dt><dd>{analysisStatus}</dd></>}
          <dt className={subtle}>{t('provenance.locatorLabel')}</dt><dd className="min-w-0 break-words">{locator ?? t('provenance.notAvailable')}</dd>
        </dl>
        {analysisReasons.length > 0 && <ul className={`mt-2 list-disc space-y-0.5 pl-4 text-[10px] ${subtle}`}>{analysisReasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
        {detail && <p className={`mt-2 border-t pt-2 text-[10px] ${subtle} ${isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200'}`}>{detail}</p>}
      </div>
    </details>
  );
}
