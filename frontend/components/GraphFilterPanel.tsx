import { Check, Search } from 'lucide-react';
import { useState } from 'react';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { KnowledgeNodeIcon } from './KnowledgeNodeIcon';

export interface GraphFilterOption {
  id: string;
  label: string;
  hidden: boolean;
  color?: string;
}

interface Props {
  isDark: boolean;
  legend?: boolean;
  nodes: GraphFilterOption[];
  links: GraphFilterOption[];
  directions: GraphFilterOption[];
  onToggleNode: (id: string) => void;
  onToggleLink: (id: string) => void;
  onToggleDirection: (id: string) => void;
  onReset: () => void;
}

/** The same taxonomy is used for the full filter list and its read-only legend. */
export function GraphFilterPanel({ isDark, legend, nodes, links, directions, onToggleNode, onToggleLink, onToggleDirection, onReset }: Props) {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const groups = [
    { key: 'nodesLabel', options: nodes, toggle: onToggleNode },
    { key: 'linksLabel', options: links, toggle: onToggleLink },
    { key: 'directionFilterLabel', options: directions, toggle: onToggleDirection },
  ];
  const matches = (option: GraphFilterOption) => option.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  return (
    <div className="space-y-4 p-3">
      {legend ? <p className="text-xs text-ds-zinc-500">{t('knowledgeGraphView.legendDescription')}</p> : (
        <>
          <label className={cn('flex items-center gap-2 rounded-md border px-2', isDark ? 'border-ds-zinc-700' : 'border-ds-zinc-300')}>
            <Search className="h-3.5 w-3.5 shrink-0" />
            <input value={query} onChange={event => setQuery(event.target.value)} aria-label={t('knowledgeGraphView.searchFilters')}
              placeholder={t('knowledgeGraphView.searchFilters')} className="h-8 w-full min-w-0 bg-transparent text-xs outline-none" />
          </label>
          <button onClick={onReset} className="text-xs text-ds-indigo-400 underline underline-offset-2">{t('knowledgeGraphView.showAllTypes')}</button>
        </>
      )}
      {groups.map(group => {
        const options = group.options.filter(matches);
        if (!group.options.length) return null;
        return (
          <fieldset key={group.key} className="min-w-0 space-y-1">
            <legend className="mb-2 text-xs font-semibold">{t(`knowledgeGraphView.${group.key}`)}</legend>
            {options.map(option => {
              const content = <>
                {group.key === 'nodesLabel' ? <KnowledgeNodeIcon node={null} category={option.id} className="h-3.5 w-3.5 shrink-0 text-ds-indigo-400" />
                  : option.color ? <span className="h-0.5 w-4 shrink-0" style={{ background: option.color }} /> : null}
                <span className="min-w-0 flex-1 break-words text-left">{option.label}</span>
                {!legend && <Check aria-hidden="true" className={cn('h-3.5 w-3.5 shrink-0', option.hidden ? 'invisible' : 'text-ds-indigo-400')} />}
              </>;
              const classes = cn('flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs', option.hidden && 'text-ds-zinc-500',
                !legend && (isDark ? 'hover:bg-ds-zinc-800 focus-visible:bg-ds-zinc-800' : 'hover:bg-ds-zinc-100 focus-visible:bg-ds-zinc-100'));
              return legend ? <div key={option.id} className={classes}>{content}</div>
                : <button key={option.id} aria-pressed={!option.hidden} onClick={() => group.toggle(option.id)} className={classes}>{content}</button>;
            })}
          </fieldset>
        );
      })}
      {!legend && ![...nodes, ...links, ...directions].some(matches) && <p className="text-xs text-ds-zinc-500">{t('knowledgeGraphView.noMatchingFilters')}</p>}
    </div>
  );
}
