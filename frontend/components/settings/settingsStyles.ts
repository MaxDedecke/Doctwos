import { cn } from '@/lib/utils';

/**
 * Gemeinsame Gestaltungsbausteine der Einstellungs-Tabs. Sie fassen die Muster
 * zusammen, die Projekte, Wissensquellen, Teams, Nutzer, Logs und Auswertung
 * bereits verwenden (Radius `rounded-lg`, uppercase Abschnittsüberschriften,
 * themenabhängige Karten/Eingaben, Primärbutton in Indigo), damit IDE / MCP,
 * AI-Parameter und System & SSO nicht davon abweichen.
 */
type Theme = string;
const isDark = (theme: Theme) => theme === 'dark';

/** Wurzelcontainer eines Tabs. */
export const settingsRoot = 'space-y-6 w-full min-w-0 animate-in fade-in duration-200';

/** Abschnittsüberschrift und Feldbeschriftung (uppercase, Tracking). */
export const sectionTitleClass = (theme: Theme) =>
  cn('text-xs font-bold uppercase tracking-wide', isDark(theme) ? 'text-ds-zinc-400' : 'text-ds-zinc-500');

/** Erläuternder Fließtext unter Überschriften. */
export const helpTextClass = 'text-[0.6875rem] leading-relaxed text-ds-zinc-500';

/** Hervorgehobener Wert im Fließtext / Kartentitel. */
export const strongTextClass = (theme: Theme) =>
  cn('font-semibold', isDark(theme) ? 'text-ds-zinc-100' : 'text-ds-zinc-800');

/** Karte / Listenzeile. */
export const cardClass = (theme: Theme) =>
  cn('rounded-lg border transition-colors', isDark(theme) ? 'bg-ds-zinc-950/20 border-ds-zinc-800/80' : 'bg-ds-zinc-50 border-ds-zinc-200');

/** Hervorgehobene (aktive) Karte. */
export const activeCardClass = (theme: Theme) =>
  cn('rounded-lg border transition-colors', isDark(theme) ? 'bg-ds-indigo-500/5 border-ds-indigo-500/40' : 'bg-ds-indigo-50/40 border-ds-indigo-400');

/** Eingabefeld (Text, Zahl, Passwort). */
export const inputClass = (theme: Theme) =>
  cn(
    'w-full h-9 rounded-lg text-xs font-semibold px-3 border transition-colors outline-none',
    isDark(theme)
      ? 'bg-ds-zinc-950 border-ds-zinc-800 text-ds-zinc-100 focus:border-ds-zinc-700'
      : 'bg-ds-white border-ds-zinc-200 text-ds-zinc-800 focus:border-ds-zinc-300',
  );

/** Primäraktion. */
export const primaryButtonClass =
  'bg-transparent border border-ds-zinc-300 dark:border-ds-zinc-700 text-ds-zinc-800 dark:text-ds-zinc-100 hover:bg-ds-zinc-500/10 rounded-lg px-3.5 h-9 text-xs font-bold flex items-center gap-1.5 transition-all shrink-0';

/** Sekundäraktion (Outline). */
export const secondaryButtonClass = (theme: Theme) =>
  cn(
    'h-8 text-[0.625rem] px-2.5 rounded-lg flex items-center gap-1.5 shrink-0 focus:ring-0',
    isDark(theme)
      ? 'bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300'
      : 'bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700',
  );

/** Zurückhaltende Icon-Aktion. */
export const ghostIconButtonClass = 'h-8 w-8 rounded-lg text-ds-zinc-500 hover:bg-ds-zinc-500/10';

/** Löschen-Aktion. */
export const dangerIconButtonClass =
  'h-8 w-8 rounded-lg text-ds-red-500 border border-ds-red-500/20 hover:border-ds-red-500/40 hover:bg-ds-red-500/10';

/** Leerer Zustand. */
export const emptyStateClass = (theme: Theme) =>
  cn('text-xs italic p-3.5 border rounded-lg transition-colors', isDark(theme) ? 'text-ds-zinc-500 bg-ds-zinc-950/40 border-ds-zinc-800/60' : 'text-ds-zinc-500 bg-ds-zinc-50 border-ds-zinc-200');

/** Trennlinie innerhalb einer Karte. */
export const dividerClass = (theme: Theme) => cn('border-t', isDark(theme) ? 'border-ds-zinc-800/60' : 'border-ds-zinc-200/80');

/** Kleines Statusabzeichen (nur für Status, siehe Design Guidelines). */
export const badgeClass = (tone: 'neutral' | 'success' | 'warning' | 'accent' | 'danger') =>
  cn(
    'px-1.5 py-0.5 rounded text-[0.5625rem] font-bold uppercase tracking-wider border leading-none',
    tone === 'success' && 'bg-ds-emerald-500/10 text-ds-emerald-600 dark:text-ds-emerald-400 border-ds-emerald-500/20',
    tone === 'warning' && 'bg-ds-amber-500/10 text-ds-amber-600 dark:text-ds-amber-400 border-ds-amber-500/20',
    tone === 'accent' && 'bg-ds-indigo-500/10 text-ds-indigo-600 dark:text-ds-indigo-400 border-ds-indigo-500/20',
    tone === 'danger' && 'bg-ds-red-500/10 text-ds-red-600 dark:text-ds-red-400 border-ds-red-500/20',
    tone === 'neutral' && 'bg-ds-zinc-500/10 text-ds-zinc-500 border-ds-zinc-500/20',
  );
