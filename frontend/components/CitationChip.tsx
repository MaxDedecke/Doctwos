import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip } from '@/lib/analysisStatus';
import { compactCitationLabel, splitPlainPaths } from '@/lib/citationLabel';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn, copyToClipboard } from '@/lib/utils';
import type { KnownSource } from '@/components/MarkdownContent';
import { BookOpen, Check, Code, Copy, ExternalLink } from 'lucide-react';
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

/** Im Chat stehen Dateizitate gekürzt im Text; Dokumentansichten zeigen sie wie geschrieben. */
export const CompactCitationsContext = createContext(false);

const OPEN_DELAY_MS = 200;
const CLOSE_DELAY_MS = 150;

type OnFileClick = (filePath: string, line?: number, sourceId?: string) => void;

/** Kleiner Warn-Punkt an einem Zitat-Badge, dessen Datei nicht uneingeschränkt
 * analysiert ist (O-120) -- dieselbe Farbcodierung wie im Editor-Dateibaum
 * (FileTreeList) und im Call-Graph (CallGraphView). */
const AnalysisStatusDot: React.FC<{ source: KnownSource }> = ({ source }) =>
  source.analysis_status ? (
    <span
      data-testid="analysis-status-dot"
      className="w-1.5 h-1.5 rounded-full shrink-0"
      style={{ backgroundColor: ANALYSIS_STATUS_COLOR_TOKEN[source.analysis_status] }}
    />
  ) : null;

interface CitationChipProps {
  /** Das Zitat, wie das Modell es geschrieben hat. */
  cited: string;
  path: string;
  line?: number;
  isDoc: boolean;
  source?: KnownSource;
  id?: string;
  theme: string;
  onFileClick: OnFileClick;
}

export const CitationChip: React.FC<CitationChipProps> = ({ cited, path, line, isDoc, source, id, theme, onFileClick }) => {
  const { t } = useLanguage();
  const compact = useContext(CompactCitationsContext);
  const statusNote = source?.analysis_status
    ? formatAnalysisStatusTooltip({ status: source.analysis_status, reasons: source.analysis_reasons || [] }, t)
    : undefined;
  const open = () => onFileClick(path, line, source?.source_id != null ? String(source.source_id) : undefined);

  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [copied, setCopied] = useState(false);
  const chipRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const schedule = useCallback((action: () => void, delay: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(action, delay);
  }, []);
  const keepOpen = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);
  const showCard = () => schedule(() => setAnchor(chipRef.current?.getBoundingClientRect() ?? null), OPEN_DELAY_MS);
  const hideCard = () => schedule(() => setAnchor(null), CLOSE_DELAY_MS);

  useEffect(() => keepOpen, [keepOpen]);
  useEffect(() => {
    if (!anchor) return;
    const close = () => setAnchor(null);
    window.addEventListener('scroll', close, true);
    return () => window.removeEventListener('scroll', close, true);
  }, [anchor]);

  const chip = (
    <button
      ref={chipRef}
      type="button"
      id={id}
      onClick={open}
      title={compact ? undefined : statusNote}
      aria-label={compact ? cited : undefined}
      onKeyDown={compact ? (event) => {
        if (event.key === 'Escape') setAnchor(null);
        // Die Karte liegt im Portal; ohne das erreicht die Tastatur ihre Aktionen nicht.
        if (event.key === 'Tab' && !event.shiftKey && anchor && cardRef.current) {
          event.preventDefault();
          cardRef.current.querySelector('button')?.focus();
        }
      } : undefined}
      className={cn(
        "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs inline-flex items-center gap-1 border transition-all cursor-pointer align-middle max-w-full truncate",
        theme === 'dark'
          ? "bg-ds-indigo-500/10 text-ds-indigo-400 hover:bg-ds-indigo-500/20 border-ds-indigo-500/20"
          : "bg-ds-indigo-50 text-ds-indigo-650 hover:bg-ds-indigo-100 border-ds-indigo-200"
      )}
      {...(compact ? { onMouseEnter: showCard, onMouseLeave: hideCard, onFocus: showCard, onBlur: hideCard } : {})}
    >
      {isDoc ? <BookOpen className="w-3 h-3 text-ds-emerald-400 shrink-0" /> : <Code className="w-3 h-3 shrink-0" />}
      <span className="truncate">{compact ? compactCitationLabel(cited) : cited}</span>
      {source && <AnalysisStatusDot source={source} />}
    </button>
  );
  if (!compact) return chip;

  const actionClass = cn(
    "flex items-center gap-1.5 rounded px-2 py-1 font-medium transition-colors",
    theme === 'dark' ? "text-ds-zinc-300 hover:bg-ds-zinc-800" : "text-ds-zinc-750 hover:bg-ds-zinc-100"
  );
  return (
    <>
      {chip}
      {anchor && typeof document !== 'undefined' && createPortal(
        <div
          ref={cardRef}
          role="group"
          aria-label={path}
          onMouseEnter={keepOpen}
          onMouseLeave={hideCard}
          onFocus={keepOpen}
          onBlur={hideCard}
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return;
            setAnchor(null);
            chipRef.current?.focus();
          }}
          style={{
            position: 'fixed',
            zIndex: 1000,
            left: Math.max(8, Math.min(anchor.left, window.innerWidth - 8 - Math.min(448, window.innerWidth - 16))),
            ...(anchor.top > 130 ? { bottom: window.innerHeight - anchor.top + 4 } : { top: anchor.bottom + 4 }),
          }}
          className={cn(
            "w-[min(28rem,calc(100vw-1rem))] rounded-md border p-2 text-xs shadow-xl",
            theme === 'dark' ? "border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-200" : "border-ds-zinc-200 bg-ds-white text-ds-zinc-800"
          )}
        >
          <p className="break-all px-2 py-1 font-mono">{path}</p>
          {statusNote && <p className="px-2 pb-1 text-[0.6875rem] opacity-70">{statusNote}</p>}
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <button
              type="button"
              className={actionClass}
              onClick={async () => {
                if (!await copyToClipboard(path)) return;
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-ds-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? t('common.copied') : t('chatView.citationCopyPath')}
            </button>
            <button
              type="button"
              className={actionClass}
              onClick={() => {
                setAnchor(null);
                open();
              }}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {t(isDoc ? 'chatView.citationOpenDocument' : 'chatView.citationOpenCode')}
            </button>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

/** Ein Pfad gehört nur dann zu einer bekannten Quelle, wenn er sie vollständig oder als Pfadende trifft. */
function sourceForPath(path: string, sources: KnownSource[] | undefined): KnownSource | undefined {
  const wanted = path.replace(/\\/g, '/').toLowerCase();
  return sources?.find((source) => {
    const file = source.file.toLowerCase();
    return file === wanted || file.endsWith(`/${wanted}`) || wanted.endsWith(`/${file}`);
  });
}

/** Fließtext, in dem das Modell Dateipfade ohne Backticks ausgeschrieben hat. */
export const TextWithPaths: React.FC<{ text: string; knownSources?: KnownSource[]; theme: string; onFileClick: OnFileClick }> = ({ text, knownSources, theme, onFileClick }) => {
  const compact = useContext(CompactCitationsContext);
  if (!compact) return <>{text}</>;
  return (
    <>
      {splitPlainPaths(text).map((part, index) => {
        if (typeof part === 'string') return part;
        const source = sourceForPath(part.path, knownSources);
        return (
          <CitationChip
            key={index}
            cited={part.cited}
            path={source?.file ?? part.path}
            line={part.line}
            isDoc={source !== undefined || /\.(pdf|docx|doc|md|txt)$/i.test(part.path)}
            source={source}
            theme={theme}
            onFileClick={onFileClick}
          />
        );
      })}
    </>
  );
};
