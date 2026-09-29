import { cn } from '@/lib/utils';
import type { CSSProperties, ReactNode } from 'react';

type Tone = 'amber' | 'indigo';

// Tailwind erkennt nur vollständig ausgeschriebene Klassen, daher stehen die Töne als feste Zeichenketten hier.
const TONES: Record<Tone, { base: string; hover: string; text: string; ring: string }> = {
  amber: {
    base: 'border-ds-amber-500/60 bg-ds-amber-500/10 text-ds-amber-500',
    hover: 'hover:bg-ds-amber-500 focus-visible:bg-ds-amber-500',
    text: 'group-hover/expand:text-ds-black group-focus-visible/expand:text-ds-black',
    ring: 'focus-visible:ring-ds-amber-400',
  },
  indigo: {
    base: 'border-ds-indigo-500/60 bg-ds-indigo-500/10 text-ds-indigo-400',
    hover: 'hover:bg-ds-indigo-600 focus-visible:bg-ds-indigo-600',
    text: 'group-hover/expand:text-ds-white group-focus-visible/expand:text-ds-white',
    ring: 'focus-visible:ring-ds-indigo-400',
  },
};

// Feste Breiten links und rechts vom Text: Icon (7 + 14 px) + Abstand 8 px links, Auslauf rechts.
const ICON_AREA_PX = 29;
const TRAILING_PX = 12;
const CHAR_WIDTH_PX = 5.4;

/** Breite des ausgefahrenen Buttons; folgt der Beschriftung, damit sie in jeder Sprache hineinpasst. */
export function expandedWidthPx(label: string): number {
  return ICON_AREA_PX + Math.ceil(label.length * CHAR_WIDTH_PX) + TRAILING_PX;
}

interface HoverExpandButtonProps {
  icon: ReactNode;
  label: string;
  tone: Tone;
  onClick: () => void;
  disabled?: boolean;
  /** Tooltip; Standard ist die Beschriftung. */
  title?: string;
  ariaExpanded?: boolean;
  testId?: string;
}

/**
 * Kompakter Aktionsbutton: im Ruhezustand nur das Icon (28 px), bei Hover oder Tastaturfokus fährt er
 * mit der Beschriftung aus. Spart dauerhaft Platz in Kopfzeilen und bleibt über aria-label und den
 * unsichtbaren Text für Screenreader und Tests vollständig benannt.
 */
export function HoverExpandButton({ icon, label, tone, onClick, disabled, title, ariaExpanded, testId }: HoverExpandButtonProps) {
  const style = TONES[tone];
  return (
    <button
      type="button"
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
      title={title ?? label}
      aria-label={label}
      aria-expanded={ariaExpanded}
      style={{ '--expand-w': `${expandedWidthPx(label)}px` } as CSSProperties}
      className={cn(
        'group/expand inline-flex h-7 w-7 items-center overflow-hidden rounded-md border transition-[width,background-color] duration-200 ease-out motion-reduce:transition-none',
        'hover:w-[var(--expand-w)] focus-visible:w-[var(--expand-w)] focus-visible:outline-none focus-visible:ring-2',
        'disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:w-7',
        style.base, style.hover, style.ring,
      )}
    >
      <span className={cn('ml-[7px] flex h-3.5 w-3.5 shrink-0 items-center justify-center transition-colors', style.text)}>{icon}</span>
      <span className={cn('ml-2 whitespace-nowrap text-[0.625rem] font-semibold opacity-0 transition-opacity duration-150 group-hover/expand:opacity-100 group-focus-visible/expand:opacity-100', style.text)}>
        {label}
      </span>
    </button>
  );
}
