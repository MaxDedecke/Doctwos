import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip } from '@/lib/analysisStatus';
import { compactCitationLabel, splitPlainPaths } from '@/lib/citationLabel';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { PathHoverCard, type PathCardTrigger } from '@/components/PathHoverCard';
import type { KnownSource } from '@/components/MarkdownContent';
import { BookOpen, Code } from 'lucide-react';
import React, { createContext, useContext } from 'react';

/** Im Chat stehen Dateizitate gekürzt im Text; Dokumentansichten zeigen sie wie geschrieben. */
export const CompactCitationsContext = createContext(false);

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

  const renderChip = (trigger?: PathCardTrigger) => (
    <button
      type="button"
      id={id}
      onClick={open}
      title={compact ? undefined : statusNote}
      aria-label={compact ? cited : undefined}
      className={cn(
        "px-1.5 py-0.5 mx-0.5 rounded font-mono text-xs inline-flex items-center gap-1 border transition-all cursor-pointer align-middle max-w-full truncate",
        theme === 'dark'
          ? "bg-ds-indigo-500/10 text-ds-indigo-400 hover:bg-ds-indigo-500/20 border-ds-indigo-500/20"
          : "bg-ds-indigo-50 text-ds-indigo-650 hover:bg-ds-indigo-100 border-ds-indigo-200"
      )}
      {...trigger}
    >
      {isDoc ? <BookOpen className="w-3 h-3 text-ds-emerald-400 shrink-0" /> : <Code className="w-3 h-3 shrink-0" />}
      <span className="truncate">{compact ? compactCitationLabel(cited) : cited}</span>
      {source && <AnalysisStatusDot source={source} />}
    </button>
  );
  if (!compact) return renderChip();
  return <PathHoverCard path={path} theme={theme} note={statusNote} onView={open}>{renderChip}</PathHoverCard>;
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
