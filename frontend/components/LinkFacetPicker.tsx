import { Check } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { Facet, FacetGroup, FacetValue } from '@/lib/linkSets';
import { cn } from '@/lib/utils';

interface Props {
  facet: Facet;
  title: string;
  selected: string[];
  groupLabel: (key: string) => string;
  valueLabel: (value: FacetValue) => string;
  formatCount: (value: number) => string;
  allOfLabel: (group: string) => string;
  moreLabel: (count: number) => string;
  lessLabel: string;
  chosenLabel: (count: number) => string;
  onToggle: (value: string, checked: boolean) => void;
  onGroup: (group: FacetGroup, checked: boolean) => void;
}

// Große Gruppen zeigen zuerst die häufigsten Werte; der Rest kommt auf Wunsch dazu (Werte sind nach Anzahl sortiert).
const VISIBLE_VALUES = 18;

function MixedCheckbox({ checked, mixed, label, onChange }: { checked: boolean; mixed: boolean; label: string; onChange: (value: boolean) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = mixed; }, [mixed]);
  return <input ref={ref} type="checkbox" aria-label={label} checked={checked} className="h-3.5 w-3.5 accent-primary"
    onChange={event => onChange(event.target.checked)} />;
}

/** Ein Wert als umschaltbare Marke; darunter ein echtes Kontrollkästchen für Tastatur und Screenreader. */
function ValueChip({ value, text, count, checked, onChange }: { value: string; text: string; count: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label title={text} data-value={value}
    className={cn('inline-flex max-w-full cursor-pointer select-none items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
      'has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring',
      checked ? 'border-primary bg-primary font-medium text-primary-foreground' : 'border-border text-foreground hover:border-primary/60 hover:bg-muted')}>
    <input type="checkbox" className="sr-only" checked={checked} onChange={event => onChange(event.target.checked)} />
    {checked && <Check aria-hidden className="h-3 w-3 shrink-0" />}
    <span className="min-w-0 truncate">{text}</span>
    <span className={cn('shrink-0 tabular-nums', checked ? 'text-primary-foreground/80' : 'text-muted-foreground')}>{count}</span>
  </label>;
}

function FacetGroupBlock({ group, showHeader, props }: { group: FacetGroup; showHeader: boolean; props: Props }) {
  const [expanded, setExpanded] = useState(false);
  const chosen = group.values.filter(value => props.selected.includes(value.value)).length;
  // Gewählte Werte bleiben auch eingeklappt sichtbar.
  const visible = expanded ? group.values
    : group.values.filter((value, index) => index < VISIBLE_VALUES || props.selected.includes(value.value));
  const hidden = group.values.length - visible.length;
  const label = props.groupLabel(group.key);
  return <div className="space-y-2">
    {showHeader && <div className="flex items-center gap-2 text-xs">
      <MixedCheckbox label={props.allOfLabel(label)} checked={chosen === group.values.length}
        mixed={chosen > 0 && chosen < group.values.length} onChange={checked => props.onGroup(group, checked)} />
      <span className="font-medium">{label}</span>
      <span className="tabular-nums text-muted-foreground">{props.formatCount(group.count)}</span>
    </div>}
    <div className={cn('flex flex-wrap gap-1.5', showHeader && 'pl-5')}>
      {visible.map(value => <ValueChip key={value.value} value={value.value} text={props.valueLabel(value)}
        count={props.formatCount(value.count)} checked={props.selected.includes(value.value)}
        onChange={checked => props.onToggle(value.value, checked)} />)}
      {group.values.length > VISIBLE_VALUES && <button type="button" onClick={() => setExpanded(value => !value)}
        className="rounded-full px-2 py-1 text-xs text-primary underline-offset-2 hover:underline">
        {expanded ? props.lessLabel : props.moreLabel(hidden)}
      </button>}
    </div>
  </div>;
}

/** Eine Facette (Typ je Sprache, Repository, Wissensquelle) als Gruppen von Marken; Gruppen lassen sich ganz wählen. */
export function LinkFacetPicker(props: Props) {
  const { facet, title, selected } = props;
  const showHeaders = facet.groups.length > 1;
  return <fieldset data-testid={`facet-${facet.name}`} className="min-w-0 space-y-3">
    <legend className="mb-2 flex w-full items-baseline gap-2 text-xs font-semibold">
      <span>{title}</span>
      {selected.length > 0 && <span className="font-normal text-muted-foreground">{props.chosenLabel(selected.length)}</span>}
    </legend>
    {facet.groups.map(group => <FacetGroupBlock key={group.key} group={group} showHeader={showHeaders} props={props} />)}
  </fieldset>;
}
