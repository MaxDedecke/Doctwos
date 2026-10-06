'use client';

import { useLanguage } from '@/lib/i18n/LanguageContext';
import { ChevronDown, Info, X } from 'lucide-react';
import React from 'react';
import { createPortal } from 'react-dom';

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
  /**
   * `dropdown`: Kurzzeile mit Aufklappbereich (Standard). `dialog`: nur das Info-Symbol, die Details
   * öffnen in einem Dialog – spart in Chat-Antworten Platz und gibt den Details mehr Raum.
   */
  variant?: 'dropdown' | 'dialog';
}

/** Compact, shared disclosure for source, revision, review state, and locator. */
export function ProvenanceDisclosure({ provenance, theme, className = '', variant = 'dropdown' }: Props) {
  const { t, language } = useLanguage();
  const [dialogOpen, setDialogOpen] = React.useState(false);
  React.useEffect(() => {
    if (!dialogOpen) return;
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setDialogOpen(false); };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [dialogOpen]);
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

  const textSize = variant === 'dialog' ? 'text-xs' : 'text-[0.625rem]';
  const details = (
    <>
        <dl className={`grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 ${textSize}`}>
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
        {analysisReasons.length > 0 && <ul className={`mt-3 list-disc space-y-0.5 pl-4 ${textSize} ${subtle}`}>{analysisReasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
        {detail && <p className={`mt-3 border-t pt-3 ${textSize} ${subtle} ${isDark ? 'border-ds-zinc-800' : 'border-ds-zinc-200'}`}>{detail}</p>}
    </>
  );

  if (variant === 'dialog') {
    const label = `${valueFor('kind')} · ${valueFor('status')}`;
    return (
      <>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          title={label}
          aria-label={label}
          aria-haspopup="dialog"
          className={`inline-flex shrink-0 items-center justify-center rounded p-1 transition-colors ${className} ${summaryText}`}
        >
          <Info className="h-3.5 w-3.5" />
        </button>
        {dialogOpen && typeof document !== 'undefined' && createPortal(
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center bg-ds-black/70 p-4 backdrop-blur-sm"
            onMouseDown={(event) => { if (event.target === event.currentTarget) setDialogOpen(false); }}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-label={label}
              className={`max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-lg border p-5 shadow-2xl ${panel}`}
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className={`text-sm font-semibold ${isDark ? 'text-ds-zinc-100' : 'text-ds-zinc-900'}`}>{valueFor('kind')}</div>
                  <div className={`text-xs ${subtle}`}>{valueFor('status')}</div>
                </div>
                <button
                  type="button"
                  onClick={() => setDialogOpen(false)}
                  aria-label={t('common.close')}
                  className={`shrink-0 rounded p-1 transition-colors ${summaryText}`}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              {details}
            </div>
          </div>,
          document.body,
        )}
      </>
    );
  }

  return (
    <details className={`group min-w-0 max-w-full ${className}`}>
      <summary className={`inline-flex max-w-full cursor-pointer list-none items-center gap-1 rounded px-1.5 py-1 text-[0.625rem] ${summaryText} [&::-webkit-details-marker]:hidden`}>
        <Info className="h-3 w-3 shrink-0" />
        <span className="truncate">{valueFor('kind')}</span>
        <span className="truncate">· {valueFor('status')}</span>
        <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className={`mt-1 w-[min(22rem,calc(100vw-2rem))] max-w-full rounded-md border p-2.5 shadow-xl ${panel}`}>
        {details}
      </div>
    </details>
  );
}
