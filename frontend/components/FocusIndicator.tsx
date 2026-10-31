import { PathHoverCard } from '@/components/PathHoverCard';
import { getEntityTypeLabel, type GraphLocale } from '@/lib/graphTaxonomy';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { PanelSelection } from '@/lib/panelHistory';
import { cn } from '@/lib/utils';
import { BookOpen, Braces, Globe, Terminal, X, type LucideIcon } from 'lucide-react';
import React from 'react';

export interface FocusInfo {
  Icon: LucideIcon;
  label: string;
  kind: string;
  path: string;
  colorClass: string;
}

const fileName = (path: string) => path.split('/').pop() || path;

/** Das Objekt einer Auswahl: Code-Objekt vor Dokument vor Datei. */
export function getFocusInfo(
  selection: Pick<PanelSelection, 'selectedEntity' | 'selectedDoc' | 'selectedFile'>,
  t: (key: string) => string,
  language: GraphLocale,
): FocusInfo | null {
  const { selectedEntity: entity, selectedDoc: doc, selectedFile: file } = selection;
  if (entity) {
    return {
      Icon: Braces,
      label: entity.name,
      kind: getEntityTypeLabel(entity.type, language) || t('page.focusBar.entity'),
      path: entity.file_path || file || entity.name,
      colorClass: 'text-ds-indigo-400',
    };
  }
  if (doc) {
    const isWeb = doc.isWebOrigin || ['confluence', 'jira'].includes((doc.type || '').toLowerCase());
    return {
      Icon: isWeb ? Globe : BookOpen,
      label: isWeb ? doc.name : fileName(doc.name),
      kind: t(isWeb ? 'page.focusBar.webOrigin' : 'page.focusBar.document'),
      path: doc.url || doc.name,
      colorClass: isWeb ? 'text-ds-emerald-400' : 'text-ds-orange-400',
    };
  }
  if (file) return { Icon: Terminal, label: fileName(file), kind: t('page.focusBar.file'), path: file, colorClass: 'text-ds-blue-400' };
  return null;
}

interface FocusIndicatorProps {
  selection: Pick<PanelSelection, 'selectedEntity' | 'selectedDoc' | 'selectedFile'>;
  theme: string;
  onView: () => void;
  onClear: () => void;
}

/** Das aktuelle Fokusobjekt des Arbeitsbereichs. Ohne Fokus erscheint nichts. */
export const FocusIndicator: React.FC<FocusIndicatorProps> = ({ selection, theme, onView, onClear }) => {
  const { t, language } = useLanguage();
  const focus = getFocusInfo(selection, t, language);
  if (!focus) return null;

  const isDark = theme === 'dark';
  return (
    // Der Key startet das kurze Aufleuchten bei jedem Fokuswechsel neu.
    <div
      key={`${focus.path}:${focus.label}`}
      className={cn(
        'doctus-focus-flash flex h-9 min-w-0 max-w-[24rem] items-center rounded-md border text-[0.6875rem]',
        isDark ? 'border-ds-zinc-800 bg-ds-zinc-900' : 'border-ds-zinc-200 bg-ds-white',
      )}
    >
      <PathHoverCard path={focus.path} theme={theme} onView={onView}>
        {(trigger) => (
          <button
            {...trigger}
            type="button"
            onClick={onView}
            aria-label={`${t('page.focusBar.current')}: ${focus.label} (${focus.kind})`}
            className="flex h-full min-w-0 cursor-pointer items-center gap-1.5 rounded-l-md pl-2.5 pr-1.5"
          >
            <focus.Icon className={cn('h-3.5 w-3.5 shrink-0', focus.colorClass)} />
            <span className={cn('hidden truncate font-medium sm:inline', isDark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>{focus.label}</span>
            <span className="hidden shrink-0 text-[0.625rem] text-ds-zinc-500 lg:inline">· {focus.kind}</span>
          </button>
        )}
      </PathHoverCard>
      <button
        type="button"
        onClick={onClear}
        title={t('page.focusBar.clear')}
        aria-label={t('page.focusBar.clear')}
        className={cn(
          'mr-1 shrink-0 cursor-pointer rounded p-1 transition-colors',
          isDark ? 'text-ds-zinc-500 hover:bg-ds-zinc-800 hover:text-ds-zinc-200' : 'text-ds-zinc-400 hover:bg-ds-zinc-100 hover:text-ds-zinc-700',
        )}
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
};
