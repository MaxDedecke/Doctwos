import { cn } from '@/lib/utils';
import React from 'react';

const TONES = [
  'bg-ds-indigo-500/15 text-ds-indigo-600 dark:text-ds-indigo-400 border-ds-indigo-500/25',
  'bg-ds-sky-500/15 text-ds-sky-600 dark:text-ds-sky-400 border-ds-sky-500/25',
  'bg-ds-emerald-500/15 text-ds-emerald-600 dark:text-ds-emerald-400 border-ds-emerald-500/25',
  'bg-ds-amber-500/15 text-ds-amber-600 dark:text-ds-amber-400 border-ds-amber-500/25',
  'bg-ds-red-500/15 text-ds-red-600 dark:text-ds-red-400 border-ds-red-500/25',
];

function initialsOf(label: string): string {
  const parts = label.trim().split(/[\s._@-]+/).filter(Boolean);
  if (parts.length === 0) return '?';
  const first = parts[0].charAt(0);
  const second = parts.length > 1 ? parts[1].charAt(0) : parts[0].charAt(1);
  return (first + second).toUpperCase();
}

/** Runder Avatar mit Initialen; die Farbe ergibt sich stabil aus dem Namen. */
export const InitialsAvatar: React.FC<{ label: string; className?: string }> = ({ label, className }) => {
  let hash = 0;
  for (const ch of label) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-[0.6875rem] font-bold select-none',
        TONES[hash % TONES.length],
        className,
      )}
    >
      {initialsOf(label)}
    </span>
  );
};
