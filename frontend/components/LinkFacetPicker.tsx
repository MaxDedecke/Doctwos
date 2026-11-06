import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Facet, FacetGroup, FacetValue } from '@/lib/linkSets';

interface Props {
  facet: Facet;
  title: string;
  selected: string[];
  groupLabel: (key: string) => string;
  valueLabel: (value: FacetValue) => string;
  formatCount: (value: number) => string;
  allOfLabel: (group: string) => string;
  onToggle: (value: string, checked: boolean) => void;
  onGroup: (group: FacetGroup, checked: boolean) => void;
}

function MixedCheckbox({ checked, mixed, label, onChange }: { checked: boolean; mixed: boolean; label: string; onChange: (value: boolean) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = mixed; }, [mixed]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked}
    onClick={event => event.stopPropagation()} onChange={event => onChange(event.target.checked)} />;
}

// Kleine Facetten und Gruppen stehen offen; große bleiben zu, bis man sie öffnet oder darin etwas gewählt ist.
const OPEN_FACET_VALUES = 30;
const OPEN_GROUP_VALUES = 12;

/** `<details>` mit eigenem Zustand: Anhaken darin klappt es nicht wieder zu. */
function Collapsible({ initiallyOpen, className, summary, children, testId }: { initiallyOpen: boolean; className: string; summary: ReactNode; children: ReactNode; testId?: string }) {
  const [open, setOpen] = useState(initiallyOpen);
  return <details data-testid={testId} open={open} onToggle={event => setOpen(event.currentTarget.open)} className={className}>
    {summary}
    {open && children}
  </details>;
}

/** Eine Facette mit gruppierten Werten (Typen je Sprache, Quellen je Quelltyp); Gruppen lassen sich ganz wählen. */
export function LinkFacetPicker({ facet, title, selected, groupLabel, valueLabel, formatCount, allOfLabel, onToggle, onGroup }: Props) {
  const flat = facet.groups.length === 1;
  const chosenTotal = selected.length;
  const valueRow = (value: FacetValue) => <label key={value.value} className="flex min-w-0 items-center gap-2 py-0.5 text-xs">
    <input type="checkbox" checked={selected.includes(value.value)} onChange={event => onToggle(value.value, event.target.checked)} />
    <span className="min-w-0 flex-1 truncate" title={value.label ?? value.value}>{valueLabel(value)}</span>
    <span className="shrink-0 tabular-nums text-ds-zinc-500">{formatCount(value.count)}</span>
  </label>;

  const valueTotal = facet.groups.reduce((sum, group) => sum + group.values.length, 0);
  return <Collapsible testId={`facet-${facet.name}`} initiallyOpen={chosenTotal > 0 || valueTotal <= OPEN_FACET_VALUES}
    className="rounded-md border border-ds-zinc-500/20" summary={<summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-xs font-medium">
      <span className="min-w-0 flex-1 truncate">{title}</span>
      {chosenTotal > 0 && <span className="rounded-full bg-ds-indigo-500/15 px-2 text-[0.625rem] text-ds-indigo-400">{chosenTotal}</span>}
    </summary>}>
    <div className="max-h-72 space-y-1 overflow-y-auto px-3 pb-2">
      {flat ? facet.groups[0].values.map(valueRow) : facet.groups.map(group => {
        const chosen = group.values.filter(value => selected.includes(value.value)).length;
        const label = groupLabel(group.key);
        return <Collapsible key={group.key} initiallyOpen={chosen > 0 || group.values.length <= OPEN_GROUP_VALUES}
          className="rounded border border-ds-zinc-500/15 px-2 py-1" summary={<summary className="flex cursor-pointer items-center gap-2 text-xs">
            <MixedCheckbox label={allOfLabel(label)} checked={chosen === group.values.length}
              mixed={chosen > 0 && chosen < group.values.length} onChange={checked => onGroup(group, checked)} />
            <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
            <span className="shrink-0 tabular-nums text-ds-zinc-500">{formatCount(group.count)}</span>
          </summary>}>
          <div className="mt-1 pb-1 pl-5">{group.values.map(valueRow)}</div>
        </Collapsible>;
      })}
    </div>
  </Collapsible>;
}
